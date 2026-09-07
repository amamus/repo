# ownCloud & oCIS Ecosystem Adoption Metrics

This repository tracks open source ecosystem data for ownCloud and oCIS from the [ecosyste.ms](https://ecosyste.ms) family of APIs and generates a static report deployable to GitHub Pages.

## Overview

The project fetches data from three ecosyste.ms services:
- **packages.ecosyste.ms** - Package registry data (npm, Packagist, RubyGems, PyPI, etc.)
- **repos.ecosyste.ms** - GitHub/GitLab repository metadata and release download counts
- **docker.ecosyste.ms** - Docker image dependent-package data

## Features

- ✅ **Real Download Counters**: npm, Packagist, RubyGems package download statistics
- 📈 **Partial Adoption Signals**: GitHub release asset downloads, Docker dependent counts
- ❌ **Not Covered**: Clearly lists what's NOT available via ecosyste.ms APIs

## Structure

```
.
├── fetch_data.py          # Main data fetching and report generation script
├── docs/                  # Static site output (GitHub Pages root)
│   └── index.html         # Generated report with Chart.js visualizations
├── data/                  # Raw API response cache (not committed)
├── .github/workflows/     # GitHub Actions workflows
│   └── update-data.yml    # Weekly data update workflow
├── requirements.txt       # Python dependencies
└── README.md
```

## Usage

### Local Development

1. Clone the repository:
   ```bash
   git clone https://github.com/amamus/repo.git
   cd repo
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the data fetch and generate report:
   ```bash
   python fetch_data.py
   ```

4. Open the report in your browser:
   ```bash
   open docs/index.html
   ```

### GitHub Pages Deployment

The repository is configured to:
1. Run the data fetch script every Monday at midnight UTC
2. Commit updated data and regenerated report to the repository
3. Deploy the `docs/` folder to GitHub Pages

The live report will be available at: `https://<username>.github.io/repo/`

## Data Sources

### Real Download Counters
These ecosystems provide genuine, comparable download statistics:
- **npm** - JavaScript/Node.js package downloads
- **Packagist** - PHP package installs
- **RubyGems** - Ruby gem downloads

### Partial Adoption Signals
These provide useful but not directly comparable data:
- **GitHub Release Asset Downloads** - Per-release, per-asset download counts
- **Docker Dependent Packages** - Number of packages depending on official images

### Not Covered
The following important metrics are NOT available through ecosyste.ms:
- Docker Hub total pulls
- download.owncloud.com tarball downloads
- PyPI download statistics (removed by PyPI in 2018)
- Marketplace/extension downloads
- Enterprise/on-premise deployments

## Rate Limiting

The script respects ecosyste.ms rate limits:
- 5000 requests per hour (unauthenticated)
- Implements 1-second delay between requests
- Caches responses for 1 hour to avoid redundant requests
- Retries on rate limit (429) and server errors (500)

## Configuration

Edit the following variables in `fetch_data.py` to customize:
- `OWNCLOUD_REPOS` - List of GitHub repositories to track
- `DOCKER_IMAGES` - List of Docker images to check
- `CACHE_EXPIRY_SECONDS` - Cache expiry time
- `RATE_LIMIT_DELAY` - Delay between requests

## License

This project is open source and available under the [MIT License](LICENSE).
