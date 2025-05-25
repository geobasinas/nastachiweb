import os
import gzip
import re
import varint
import tempfile
from base64 import b64decode, b64encode
from json import dumps, loads
from pathlib import Path
from requests import get
from struct import pack, unpack
from subprocess import run
from flask import Flask, render_template, request, send_file, jsonify, flash, redirect, url_for
from werkzeug.utils import secure_filename
from google.protobuf.json_format import (
    Parse,
    ParseError,
    MessageToDict,
)

app = Flask(__name__)
app.secret_key = 'tachiyomi-backup-converter-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'

# Create directories if they don't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

FORKS = {
    'mihon': 'mihonapp/mihon',
    'sy': 'jobobby04/TachiyomiSY',
    'j2k': 'Jays2Kings/tachiyomiJ2K',
    'yokai': 'null2264/yokai',
    'komikku': 'komikku-app/komikku',
}

PROTONUMBER_RE = r'(?:^\s*(?!\/\/\s*)@ProtoNumber\((?P<number>\d+)\)\s*|data class \w+\(|^)va[rl]\s+(?P<name>\w+):\s+(?:(?:(?:List|Set)<(?P<list>\w+)>)|(?P<type>\w+))(?P<optional>\?|(:?\s+=))?'
CLASS_RE = r'^(?:data )?class (?P<name>\w+)\((?P<defs>(?:[^)(]+|\((?:[^)(]+|\([^)(]*\))*\))*)\)'
DATA_TYPES = {
    'String': 'string',
    'Int': 'int32',
    'Long': 'int64',
    'Boolean': 'bool',
    'Float': 'float',
    'Char': 'string',
}

def fetch_schema(fork: str) -> list[tuple[str, str]]:
    files: list[tuple[str, str]] = []
    git = get(
        f'https://api.github.com/repos/{fork}/contents/app/src/main/java/eu/kanade/tachiyomi/data/backup/models'
    ).json()
    for entry in git:
        if entry.get('type') == 'file':
            files.append((entry.get('name'), entry.get('download_url')))
        elif entry.get('type') == 'dir':
            for sub_entry in get(entry.get('url')).json():
                if sub_entry.get('type') == 'file':
                    files.append((sub_entry.get('name'), sub_entry.get('download_url')))
    return files

def parse_model(model: str) -> list[str]:
    data = get(model).text
    message: list[str] = []
    for name in re.finditer(CLASS_RE, data, re.MULTILINE):
        message.append('message {name} {{'.format(name=name.group('name')))
        for field in re.finditer(PROTONUMBER_RE, name.group('defs'), re.MULTILINE):
            message.append(
                '  {repeated} {type} {name} = {number};'.format(
                    repeated='repeated'
                    if field.group('list')
                    else 'optional'
                    if field.group('optional')
                    else 'required',
                    type=DATA_TYPES.get(
                        field.group('type'),
                        DATA_TYPES.get(
                            field.group('list'),
                            field.group('list') or field.group('type'),
                        ),
                    ),
                    name=field.group('name'),
                    number=field.group('number') or 1
                    if not name.group('name').startswith('Broken')
                    else int(field.group('number')) + 1,
                )
            )
        message.append('}\n')
    return message

def proto_gen(file: str = None, fork: str = 'mihon'):
    schema = '''syntax = "proto2";

enum UpdateStrategy {
  ALWAYS_UPDATE = 0;
  ONLY_FETCH_ONCE = 1;
}

message PreferenceValue {
  required string type = 1;
  required bytes truevalue = 2;
}

'''.splitlines()
    print(f'... Fetching from {fork.upper()}')
    for i in fetch_schema(FORKS[fork]):
        print(f'... Parsing {i[0]}')
        schema.append(f'// {i[0]}')
        schema.extend(parse_model(i[1]))
    filename = file or f'schema-{fork}.proto'
    print(f'Writing {filename}')
    with open(filename, 'wt') as f:
        f.write('\n'.join(schema))

def ensure_schema():
    try:
        from schema_pb2 import Backup
        return Backup
    except (ModuleNotFoundError, NameError):
        print('No protobuf schema found...')
        proto_gen('schema.proto')
        print('Generating Python sources...')
        try:
            run(['protoc', '--python_out=.', '--pyi_out=.', 'schema.proto'])
        except FileNotFoundError:
            raise Exception('Protoc not found. Please install Protocol Buffers compiler.')
        try:
            from schema_pb2 import Backup
            return Backup
        except (ModuleNotFoundError, NameError):
            raise Exception('Unable to generate protobuf schema.')

def read_backup(input_path: str) -> bytes:
    if input_path.endswith('.tachibk') or input_path.endswith('.proto.gz'):
        with gzip.open(input_path, 'rb') as zip_file:
            backup_data = zip_file.read()
    else:
        with open(input_path, 'rb') as file:
            backup_data = file.read()
    return backup_data

def parse_backup(backup_data: bytes, Backup):
    message = Backup()
    message.ParseFromString(backup_data)
    return message

def readable_preference(preference_value: dict):
    true_value = preference_value['value']['truevalue']
    match preference_value['value']['type'].split('.')[-1].removesuffix('PreferenceValue'):
        case 'Boolean':
            return bool(varint.decode_bytes(b64decode(true_value)[1:]))
        case 'Int' | 'Long':
            return varint.decode_bytes(b64decode(true_value)[1:])
        case 'Float':
            return unpack('f', b64decode(true_value)[1:])[0]
        case 'String':
            return b64decode(true_value)[2:].decode('utf-8')
        case 'StringSet':
            bar = list(b64decode(true_value))
            new_list = []
            for byte in bar:
                if byte == bar[0]:
                    new_list.append([])
                    continue
                new_list[-1].append(byte)
            for index, entry in enumerate(new_list):
                new_list[index] = bytes(entry[1:]).decode('utf-8')
            return new_list
        case _:
            return None

def convert_backup_to_json(input_path: str, output_path: str, fork: str = 'mihon', convert_preferences: bool = False):
    try:
        Backup = ensure_schema()
        backup_data = read_backup(input_path)
        message = parse_backup(backup_data, Backup)
        message_dict = MessageToDict(message)

        if convert_preferences:
            print('Translating Preferences...')
            for idx, pref in enumerate(message_dict.get('backupPreferences', [])):
                message_dict['backupPreferences'][idx]['value']['truevalue'] = readable_preference(pref)
            for source_index, source in enumerate(message_dict.get('backupSourcePreferences', [])):
                for idx, pref in enumerate(source.get('prefs', [])):
                    message_dict['backupSourcePreferences'][source_index]['prefs'][idx]['value']['truevalue'] = readable_preference(pref)

        with open(output_path, 'wt') as file:
            file.write(dumps(message_dict, indent=2))
        
        return True, f'Backup successfully converted to JSON'
    except Exception as e:
        return False, f'Error converting backup: {str(e)}'

@app.route('/')
def index():
    return render_template('index.html', forks=FORKS.keys())

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file selected')
        return redirect(url_for('index'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected')
        return redirect(url_for('index'))
    
    if file:
        filename = secure_filename(file.filename)
        if not (filename.endswith('.tachibk') or filename.endswith('.proto.gz')):
            flash('Invalid file type. Please upload a .tachibk or .proto.gz file')
            return redirect(url_for('index'))
        
        # Save uploaded file
        input_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_path)
        
        # Get form options
        fork = request.form.get('fork', 'mihon')
        convert_preferences = 'convert_preferences' in request.form
        
        # Generate output filename
        base_name = os.path.splitext(filename)[0]
        if base_name.endswith('.proto'):
            base_name = os.path.splitext(base_name)[0]
        output_filename = f"{base_name}_converted.json"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        # Convert backup to JSON
        success, message = convert_backup_to_json(input_path, output_path, fork, convert_preferences)
        
        # Clean up uploaded file
        os.remove(input_path)
        
        if success:
            return render_template('result.html', 
                                 success=True, 
                                 message=message,
                                 download_file=output_filename)
        else:
            return render_template('result.html', 
                                 success=False, 
                                 message=message)

@app.route('/download/<filename>')
def download_file(filename):
    try:
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], secure_filename(filename))
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=filename)
        else:
            flash('File not found')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'Error downloading file: {str(e)}')
        return redirect(url_for('index'))

@app.route('/api/convert', methods=['POST'])
def api_convert():
    """API endpoint for programmatic access"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    fork = request.form.get('fork', 'mihon')
    convert_preferences = request.form.get('convert_preferences', 'false').lower() == 'true'
    
    try:
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.tachibk') as temp_input:
            file.save(temp_input.name)
            
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as temp_output:
                success, message = convert_backup_to_json(temp_input.name, temp_output.name, fork, convert_preferences)
                
                if success:
                    with open(temp_output.name, 'r') as f:
                        json_content = f.read()
                    
                    # Clean up temp files
                    os.unlink(temp_input.name)
                    os.unlink(temp_output.name)
                    
                    return jsonify({
                        'success': True,
                        'message': message,
                        'data': loads(json_content)
                    })
                else:
                    # Clean up temp files
                    os.unlink(temp_input.name)
                    os.unlink(temp_output.name)
                    
                    return jsonify({
                        'success': False,
                        'error': message
                    }), 500
                    
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) 