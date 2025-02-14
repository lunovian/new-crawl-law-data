# New Crawl Law Data

This repository contains a web crawler for collecting legal data. Follow the setup instructions below to get started.

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

## Setup

### 1. Clone the repository:

```bash
git clone https://github.com/yourusername/new-crawl-law-data.git
cd new-crawl-law-data
```

### 2. Create a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # For Linux/Mac
# OR
venv\Scripts\activate     # For Windows
```

### 3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Add files to batches folder, and simply run `python main.py`

## Configuration

Configure the crawler using command line arguments:

```bash
# Run in visible browser mode
python main.py --no-headless

# Enable debug logging
python main.py --debug

# Combine multiple options
python main.py --no-headless --debug
```

Available options:

- `--no-headless`: Run browser in visible mode instead of headless
- `--debug`: Enable debug logging for troubleshooting

## License

lawlicense

## Contributing

1. Fork the repository
2. Create your feature branch
3. Submit a pull request

## Contact

urmom
