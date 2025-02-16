# New Crawl Law Data

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
2. Run the crawler:

```bash
python main.py
```

The crawler will:

- Process URLs from Excel files
- Track progress in `download_urls.csv`
- Download documents to `downloads` folder
- Automatically retry failed URLs
- Handle browser sessions safely

## Configuration

Configure the crawler using command line arguments:

```bash
# Run in visible browser mode
python main.py --no-headless
```

Available options:

- `--no-headless`: Run browser in visible mode instead of headless

## Output

- `download_urls.csv`: Tracks URL processing status
- `downloads/doc/`: Word documents
- `downloads/pdf/`: PDF files
- Console progress bars and status updates

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

## Contact
