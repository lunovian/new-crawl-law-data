# Crawl Law Data

This repository contains a web crawler for collecting legal data. Follow the setup instructions below to get started.

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/new-crawl-law-data.git
cd new-crawl-law-data
```

### 2. Create a virtual environment

#### Python Environment

```bash
python -m venv venv
source venv/bin/activate  # For Linux/Mac
# OR
venv\Scripts\activate     # For Windows
```

#### Conda Environment

```bash
conda create -n lawdata python=3.12
conda activate lawdata
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install
```

## Usage

1. Add Excel files containing URLs to the `batches` folder
2. Run the crawler with desired mode:

```bash
# Full process (collect and download)
python main.py

# Collection only
python main.py --collect-only

# Download only
python main.py --download-only

# Visible mode collection
python main.py --no-headless

# Custom timeout
python main.py --timeout 180
```

The crawler will:

- Process URLs from Excel files
- Track progress in `download_urls.csv`
- Download documents to `downloads` folder
- Automatically retry failed URLs
- Handle browser sessions safely
- Clean up resources on exit

## Configuration

Configure the crawler using command line arguments:

```bash
Options:
  --no-headless     Run browser in visible mode (default: headless)
  --collect-only    Only collect URLs without downloading
  --download-only   Only process pending downloads without collecting
  --timeout SEC     Page load timeout in seconds (default: 120)
```

Note: `--collect-only` and `--download-only` cannot be used together.

## Output

### Files

- `download_urls.csv`: Tracks URL processing status
- `downloads/doc/`: Word documents
- `downloads/pdf/`: PDF files
- `logs/`: Detailed operation logs

### Status Tracking

- URL collection progress
- Download status
- Error reporting
- Final statistics

## Process Control

The crawler supports graceful interruption:

- Press Ctrl+C to initiate cleanup
- Browser processes are properly terminated
- Progress is saved
- Terminal state is restored

## License

lawlicense

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Submit a pull request

## Troubleshooting

Common issues:

- **Browser launch fails**: Update Playwright/Chrome
- **Network errors**: Check internet connection
- **Login issues**: Verify credentials
- **Permission errors**: Check folder permissions
- **Process hanging**: Use Ctrl+C to cleanly terminate

## Statistics

The crawler provides detailed statistics on completion:

- Total URLs processed
- Success/failure rates
- Download completion status
- Processing time

## Contact

<nxan2911@gmail.com>
