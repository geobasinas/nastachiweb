# 🚀 Tachiyomi Backup Converter

A modern web application that converts Tachiyomi backup files (.tachibk, .proto.gz) to readable JSON format. Built with Flask and packaged as a Docker container for easy deployment.

## ✨ Features

- **Modern Web Interface**: Beautiful, responsive UI with drag-and-drop file upload
- **JSON Viewer**: Interactive viewer with search functionality and backup statistics
- **Detailed Manga Pages**: Click any manga to see comprehensive details, chapters, and progress
- **Multi-Fork Support**: Supports Mihon, TachiyomiSY, TachiyomiJ2K, Yokai, and Komikku
- **Secure Processing**: Files are processed locally and automatically cleaned up
- **REST API**: Programmatic access for automation
- **Docker Ready**: Easy deployment with Docker and Docker Compose

## 🚀 Quick Start

### Using Docker Compose (Recommended)

1. Clone or download the project files
2. Run the application:

```bash
docker-compose up --build
```

3. Open your browser and go to `http://localhost:5000`

### Using Docker

```bash
# Build the image
docker build -t tachiyomi-converter .

# Run the container
docker run -p 5000:5000 tachiyomi-converter
```

## 📖 Usage

### Web Interface

1. Open `http://localhost:5000` in your browser
2. Drag and drop your Tachiyomi backup file or click to browse
3. Select your Tachiyomi fork (Mihon, SY, J2K, Yokai, or Komikku)
4. Optionally enable preference conversion for human-readable format
5. Click "Convert to JSON"
6. Browse your manga library in the beautiful card view
7. Click any manga card to see detailed information, chapters, and reading progress
8. Use search and filters to find specific manga
9. Toggle to raw JSON view or download the file

### API Usage

The application provides a REST API endpoint for programmatic access:

```bash
# Convert a backup file
curl -X POST \
  -F "file=@backup.tachibk" \
  -F "fork=mihon" \
  -F "convert_preferences=true" \
  http://localhost:5000/api/convert
```

**API Response:**
```json
{
  "success": true,
  "message": "Backup successfully converted to JSON",
  "data": { ... }
}
```

## 🔧 Configuration

### Environment Variables

- `FLASK_ENV`: Set to `production` for production deployment
- `PYTHONUNBUFFERED`: Set to `1` for immediate log output

### File Size Limits

- Maximum upload size: 100MB
- Supported formats: `.tachibk`, `.proto.gz`

## 🏗️ Development

### Local Development

1. Install Python 3.11+
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Install Protocol Buffers compiler:

```bash
# Ubuntu/Debian
sudo apt-get install protobuf-compiler

# macOS
brew install protobuf

# Windows
# Download from https://github.com/protocolbuffers/protobuf/releases
```

4. Run the application:

```bash
python app.py
```

### Project Structure

```
├── app.py                 # Main Flask application
├── templates/
│   ├── base.html         # Base template with styling
│   ├── index.html        # Upload page
│   └── result.html       # Results page
├── requirements.txt      # Python dependencies
├── Dockerfile           # Docker configuration
├── docker-compose.yml   # Docker Compose configuration
└── README.md           # This file
```

## 🔒 Security

- Files are processed in temporary directories and automatically cleaned up
- Input validation for file types and sizes
- Secure filename handling to prevent path traversal
- No persistent storage of uploaded files

## 🐛 Troubleshooting

### Common Issues

1. **"Protoc not found" error**: Install Protocol Buffers compiler
2. **File upload fails**: Check file size (max 100MB) and format (.tachibk, .proto.gz)
3. **Conversion fails**: Ensure you've selected the correct Tachiyomi fork

### Supported Tachiyomi Forks

- **Mihon** (default)
- **TachiyomiSY**
- **TachiyomiJ2K**
- **Yokai**
- **Komikku**

## 📝 License

This project is open source and available under the MIT License.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📞 Support

If you encounter any issues or have questions, please check the troubleshooting section or create an issue in the project repository. 