#!/usr/bin/env python3
"""
Fetch open source ecosystem data for ownCloud and oCIS from ecosyste.ms APIs.
Generates a static site in docs/ folder deployable to GitHub Pages.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# Configuration
DATA_DIR = Path("data")
DOCS_DIR = Path("docs")
CACHE_EXPIRY_SECONDS = 3600  # 1 hour cache expiry
RATE_LIMIT_DELAY = 1.0  # seconds between requests to stay under 5000/hr

# ecosyste.ms API endpoints
PACKAGES_API = "https://packages.ecosyste.ms/api/v1"
REPOS_API = "https://repos.ecosyste.ms/api/v1"
DOCKER_API = "https://docker.ecosyste.ms"

# Ecosystems that provide real download counters
REAL_DOWNLOAD_ECOSYSTEMS = {"npm", "Packagist", "RubyGems"}

# ownCloud GitHub repos to track
OWNCLOUD_REPOS = [
    "owncloud/core",
    "owncloud/ocis",
    "owncloud/ocis-mcp-server",
    "owncloud/web",
    "owncloud/web-extensions",
    "owncloud/android",
    "owncloud/ios",
    "owncloud/client",
]

# Docker images to check
DOCKER_IMAGES = [
    "owncloud",
    "owncloud/ocis",
    "owncloud/ocis-mcp-server",
    "owncloud/core",
    "owncloud/web",
    "owncloud/android",
    "owncloud/ios",
    "owncloud/client",
]

# All ecosyste.ms supported package ecosystems
PACKAGE_ECOSYSTEMS = [
    "npm", "Packagist", "RubyGems", "PyPI", "Maven", "NuGet", 
    "crates.io", "Go", "Hex", "Pub", "Conda", "Alpine", 
    "Debian", "Fedora", "Homebrew", "Chocolatey", "Scoop",
    "Cargo", "Hackage", "Clojars", "Julia",
]

# All ecosyste.ms supported repository hosts
REPO_HOSTS = ["GitHub", "GitLab"]


class APIClient:
    """Client for ecosyste.ms APIs with caching and rate limiting."""

    def __init__(self, cache_dir: Path = DATA_DIR):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "owncloud-ecosystem-stats/1.0",
            "Accept": "application/json",
        })
        self.last_request_time = 0.0

    def _get_cache_path(self, url: str) -> Path:
        """Get cache file path for a URL."""
        safe_name = url.replace("https://", "").replace("/", "_").replace("?", "-").replace("&", "-").replace("%2F", "_").replace("%252F", "_")
        return self.cache_dir / f"{safe_name[:200]}.json"

    def _is_cache_valid(self, cache_path: Path) -> bool:
        """Check if cache is still valid."""
        if not cache_path.exists():
            return False
        mtime = cache_path.stat().st_mtime
        age = time.time() - mtime
        return age < CACHE_EXPIRY_SECONDS

    def _enforce_rate_limit(self):
        """Ensure we don't exceed rate limits."""
        elapsed = time.time() - self.last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self.last_request_time = time.time()

    def get(self, url: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Get data from API with caching."""
        cache_path = self._get_cache_path(url)

        if not force_refresh and self._is_cache_valid(cache_path):
            with open(cache_path, "r") as f:
                return json.load(f)

        for attempt in range(3):
            try:
                self._enforce_rate_limit()
                response = self.session.get(url, timeout=30)
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    print(f"Rate limited, waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                
                if response.status_code == 500:
                    time.sleep(2 ** attempt)
                    continue
                    
                response.raise_for_status()
                data = response.json()

                with open(cache_path, "w") as f:
                    json.dump(data, f, indent=2)
                
                return data

            except requests.exceptions.RequestException as e:
                print(f"Request failed for {url}: {e}")
                if attempt == 2:
                    return None
                time.sleep(2 ** attempt)

        return None


def fetch_package_data(client: APIClient) -> Dict[str, Any]:
    """Fetch package data for owncloud and oCIS."""
    print("Fetching package data...")
    
    results = {"owncloud": {}, "ocis": {}}
    
    for name in ["owncloud", "ocis"]:
        url = f"{PACKAGES_API}/packages/lookup?name={name}"
        data = client.get(url)
        
        if data and isinstance(data, list):
            packages_by_ecosystem = {}
            for pkg in data:
                ecosystem = pkg.get("ecosystem", "unknown")
                if ecosystem not in packages_by_ecosystem:
                    packages_by_ecosystem[ecosystem] = []
                packages_by_ecosystem[ecosystem].append(pkg)
            
            deduped = {}
            for ecosystem, packages in packages_by_ecosystem.items():
                sorted_packages = sorted(
                    packages, 
                    key=lambda p: p.get("latest_release_published_at", ""),
                    reverse=True
                )
                if sorted_packages:
                    deduped[ecosystem] = sorted_packages[0]
            
            results[name] = deduped
        elif data and "package" in data:
            packages_by_ecosystem = {}
            for pkg in data["package"]:
                ecosystem = pkg.get("ecosystem", "unknown")
                if ecosystem not in packages_by_ecosystem:
                    packages_by_ecosystem[ecosystem] = []
                packages_by_ecosystem[ecosystem].append(pkg)
            
            deduped = {}
            for ecosystem, packages in packages_by_ecosystem.items():
                sorted_packages = sorted(
                    packages, 
                    key=lambda p: p.get("latest_release_published_at", ""),
                    reverse=True
                )
                if sorted_packages:
                    deduped[ecosystem] = sorted_packages[0]
            
            results[name] = deduped
    
    return results


def fetch_repo_data(client: APIClient) -> Dict[str, Any]:
    """Fetch GitHub repository data for ownCloud org."""
    print("Fetching repository data...")
    
    results = {}
    
    for repo_name in OWNCLOUD_REPOS:
        encoded_repo = repo_name.replace("/", "%2F")
        url = f"{REPOS_API}/hosts/GitHub/repositories/{encoded_repo}"
        data = client.get(url)
        
        if data:
            repo_data = data
            
            releases_url = f"{REPOS_API}/hosts/GitHub/repositories/{encoded_repo}/releases"
            releases_data = client.get(releases_url)
            
            if releases_data:
                repo_data["releases"] = releases_data
            else:
                repo_data["releases"] = []
            
            total_downloads = 0
            release_time_series = []
            
            for release in repo_data.get("releases", []):
                release_downloads = 0
                assets = release.get("assets", [])
                
                for asset in assets:
                    download_count = asset.get("download_count", 0)
                    if download_count:
                        release_downloads += download_count
                
                total_downloads += release_downloads
                
                published_at = release.get("published_at", release.get("created_at", ""))
                release_time_series.append({
                    "tag": release.get("tag_name", "unknown"),
                    "published_at": published_at,
                    "downloads": release_downloads,
                })
            
            repo_data["total_release_downloads"] = total_downloads
            repo_data["release_time_series"] = sorted(
                release_time_series,
                key=lambda x: x.get("published_at", ""),
                reverse=True
            )
            
            results[repo_name] = repo_data
    
    return results


def fetch_docker_data(client: APIClient) -> Dict[str, Any]:
    """Fetch Docker image data."""
    print("Fetching Docker data...")
    
    results = {}
    
    for image_name in DOCKER_IMAGES:
        url = f"{DOCKER_API}/api/v1/packages/lookup?ecosystem=Docker%20Hub&name={image_name}"
        data = client.get(url)
        
        if data and isinstance(data, list):
            for pkg in data:
                if pkg.get("name") == image_name:
                    results[image_name] = pkg
                    break
        elif data and "package" in data:
            for pkg in data["package"]:
                if pkg.get("name") == image_name:
                    results[image_name] = pkg
                    break
    
    for image_name in DOCKER_IMAGES:
        if image_name not in results:
            url = f"{DOCKER_API}/v1/repositories/{image_name}"
            data = client.get(url)
            if data:
                results[image_name] = data
    
    return results


def fetch_comprehensive_package_data(client: APIClient, base_name: str) -> Dict[str, Any]:
    """Fetch package data across all ecosystems for a given name."""
    results = {}
    
    for ecosystem in PACKAGE_ECOSYSTEMS:
        url = f"{PACKAGES_API}/packages/lookup?ecosystem={ecosystem}&name={base_name}"
        data = client.get(url)
        
        if data:
            if isinstance(data, list):
                if data:
                    results[ecosystem] = data[0]
            elif isinstance(data, dict):
                if "package" in data and data["package"]:
                    results[ecosystem] = data["package"][0]
    
    return results


def fetch_repo_across_hosts(client: APIClient, base_name: str) -> Dict[str, Any]:
    """Fetch repository data across all supported hosts."""
    results = {}
    
    for host in REPO_HOSTS:
        if host == "GitHub":
            encoded_repo = f"owncloud%2F{base_name}"
        else:
            encoded_repo = base_name
        
        url = f"{REPOS_API}/hosts/{host}/repositories/{encoded_repo}"
        data = client.get(url)
        
        if data:
            results[f"{host}/{base_name}"] = data
    
    return results


def save_raw_data(package_data: Dict, repo_data: Dict, docker_data: Dict, comprehensive_data: Dict):
    """Save raw API responses to data directory."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(DATA_DIR / "packages_raw.json", "w") as f:
        json.dump(package_data, f, indent=2)
    
    with open(DATA_DIR / "repos_raw.json", "w") as f:
        json.dump(repo_data, f, indent=2)
    
    with open(DATA_DIR / "docker_raw.json", "w") as f:
        json.dump(docker_data, f, indent=2)
    
    with open(DATA_DIR / "comprehensive_raw.json", "w") as f:
        json.dump(comprehensive_data, f, indent=2)


def generate_table_rows(downloads_list):
    """Generate HTML table rows for downloads."""
    rows = []
    for d in downloads_list:
        name = d.get('name', '')
        ecosystem = d.get('ecosystem', '')
        package = d.get('package', '') or 'N/A'
        version = d.get('version', '') or 'N/A'
        downloads = d.get('downloads', 0) or 0
        
        row = f'''                <tr>
                    <td>{name}</td>
                    <td><span class="ecosystem-tag ecosystem-real">{ecosystem}</span></td>
                    <td>{package}</td>
                    <td>{version}</td>
                    <td class="download-count">{downloads:,}</td>
                </tr>'''
        rows.append(row)
    return '\n'.join(rows)


def generate_repo_items(repo_data_list):
    """Generate HTML for repository items."""
    items = []
    for repo in repo_data_list:
        repo_name = repo.get('repo', '')
        total = repo.get('total', 0)
        
        item = f'''            <div class="repo-item">
                <div class="repo-name">{repo_name}</div>
                <div class="repo-stats">
                    Total release asset downloads: <span class="download-count">{total:,}</span>
                </div>
            </div>'''
        items.append(item)
    return '\n'.join(items)


def generate_docker_items(docker_data_list):
    """Generate HTML for Docker items."""
    items = []
    for docker in docker_data_list:
        if docker.get('dependents', 0) > 0:
            name = docker.get('name', '')
            dependents = docker.get('dependents', 0)
            
            item = f'''        <div class="repo-item">
            <div class="repo-name">{name}</div>
            <div class="repo-stats">
                Dependent packages: <span class="download-count">{dependents:,}</span>
            </div>
        </div>'''
            items.append(item)
    return '\n'.join(items)


def generate_comprehensive_table_rows(comprehensive_summary):
    """Generate HTML table rows for comprehensive provider coverage."""
    rows = []
    for repo_name, summary in comprehensive_summary.items():
        packages = ", ".join(summary['packages']) if summary['packages'] else '<span class="null-value">None</span>'
        repos = ", ".join(summary['repos']) if summary['repos'] else '<span class="null-value">None</span>'
        rows.append(f'''                <tr>
                    <td><strong>{repo_name}</strong></td>
                    <td>{packages}</td>
                    <td>{repos}</td>
                </tr>''')
    return '\n'.join(rows)


def generate_html_report(package_data: Dict, repo_data: Dict, docker_data: Dict, comprehensive_data: Dict = None):
    """Generate the static HTML report."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    owncloud_packages = package_data.get("owncloud", {})
    ocis_packages = package_data.get("ocis", {})
    
    real_downloads = []
    
    for name, packages in [("ownCloud", owncloud_packages), ("oCIS", ocis_packages)]:
        for ecosystem, pkg in packages.items():
            downloads = pkg.get("downloads", 0) or 0
            ecosystem_name = ecosystem
            
            real_downloads.append({
                "name": name,
                "ecosystem": ecosystem_name,
                "package": pkg.get("name", ""),
                "version": pkg.get("version", ""),
                "downloads": downloads,
                "is_real": ecosystem_name in REAL_DOWNLOAD_ECOSYSTEMS,
            })
    
    real_downloads_sorted = sorted(
        [d for d in real_downloads if d["is_real"]],
        key=lambda x: x["downloads"] or 0,
        reverse=True
    )
    
    repo_downloads_data = []
    for repo_name, repo_info in repo_data.items():
        total = repo_info.get("total_release_downloads", 0)
        if total > 0:
            repo_downloads_data.append({
                "repo": repo_name,
                "total": total,
                "time_series": repo_info.get("release_time_series", []),
            })
    
    repo_downloads_data.sort(key=lambda x: x["total"], reverse=True)
    
    docker_packages = []
    for image_name, pkg in docker_data.items():
        dependents = pkg.get("dependent_repos_count", 0) or pkg.get("dependent_packages_count", 0) or 0
        docker_packages.append({
            "name": image_name,
            "dependents": dependents,
        })
    
    comprehensive_summary = {}
    if comprehensive_data:
        for repo_name, data in comprehensive_data.items():
            comprehensive_summary[repo_name] = {
                "packages": list(data.get("packages", {}).keys()),
                "repos": list(data.get("repos", {}).keys()),
            }
    
    table_rows = generate_table_rows(real_downloads_sorted)
    repo_items = generate_repo_items(repo_downloads_data)
    docker_items = generate_docker_items(docker_packages)
    comprehensive_table_rows = generate_comprehensive_table_rows(comprehensive_summary)
    
    real_downloads_sorted_json = json.dumps(real_downloads_sorted)
    repo_downloads_data_json = json.dumps(repo_downloads_data)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ownCloud & oCIS Ecosystem Adoption Metrics</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        
        h1 {{
            color: #333;
            margin-bottom: 10px;
        }}
        
        .subtitle {{
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }}
        
        .timestamp {{
            font-size: 12px;
            color: #888;
            text-align: right;
            margin-bottom: 20px;
        }}
        
        .section {{
            background: white;
            border-radius: 8px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        .section h2 {{
            color: #2c3e50;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #3498db;
        }}
        
        .section .description {{
            color: #666;
            font-size: 14px;
            margin-bottom: 20px;
        }}
        
        .caveat {{
            background-color: #fff8e1;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
            border-left: 4px solid #ffc107;
        }}
        
        .caveat strong {{
            color: #ff9800;
        }}
        
        .chart-container {{
            position: relative;
            height: 400px;
            margin: 20px 0;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        
        th {{
            background-color: #f5f5f5;
            font-weight: 600;
        }}
        
        tr:hover {{
            background-color: #f9f9f9;
        }}
        
        .download-count {{
            font-family: monospace;
            font-weight: bold;
        }}
        
        .null-value {{
            color: #999;
            font-style: italic;
        }}
        
        .ecosystem-tag {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: 600;
            margin-right: 5px;
        }}
        
        .ecosystem-real {{
            background-color: #e3f2fd;
            color: #1976d2;
        }}
        
        .ecosystem-partial {{
            background-color: #f3e5f5;
            color: #7b1fa2;
        }}
        
        .ecosystem-null {{
            background-color: #f5f5f5;
            color: #666;
        }}
        
        .data-source {{
            font-size: 12px;
            color: #888;
            margin-top: 20px;
            padding-top: 10px;
            border-top: 1px solid #ddd;
        }}
        
        .not-covered {{
            background-color: #f8f8f8;
            padding: 20px;
            border-radius: 4px;
            border: 1px dashed #ccc;
        }}
        
        .not-covered h3 {{
            color: #666;
            margin-bottom: 10px;
        }}
        
        .not-covered ul {{
            list-style: none;
            padding-left: 0;
        }}
        
        .not-covered li {{
            padding: 5px 0;
            color: #888;
        }}
        
        .repo-list {{
            margin: 20px 0;
        }}
        
        .repo-item {{
            background: #f9f9f9;
            padding: 15px;
            border-radius: 4px;
            margin: 10px 0;
        }}
        
        .repo-name {{
            font-weight: bold;
            color: #333;
        }}
        
        .repo-stats {{
            margin-top: 10px;
            font-size: 14px;
            color: #666;
        }}
    </style>
</head>
<body>
    <h1>ownCloud & oCIS Ecosystem Adoption Metrics</h1>
    <p class="subtitle">Open source package and repository statistics from ecosyste.ms APIs</p>
    <p class="timestamp">Last updated: {timestamp}</p>
    
    <div class="data-source">
        <strong>Data Source:</strong> <a href="https://ecosyste.ms">ecosyste.ms</a> family of APIs
        (<a href="https://packages.ecosyste.ms">packages</a>, 
        <a href="https://repos.ecosyste.ms">repos</a>, 
        <a href="https://docker.ecosyste.ms">docker</a>)
    </div>

    <!-- Section 1: Real Download/Install Counters -->
    <div class="section">
        <h2>&#10003; Real Download/Install Counters</h2>
        <p class="description">
            These are genuine, comparable download/install statistics from package registries 
            that expose reliable counters. 
            <strong>Ecosystems tracked: npm, Packagist, RubyGems</strong>
        </p>
        
        <div class="caveat">
            <strong>&#9888;&#65039; Important:</strong> These figures represent package manager install/download counts, 
            not necessarily unique users or deployments. Different registries have different counting 
            methodologies and update frequencies.
        </div>
        
        <div class="chart-container">
            <canvas id="realDownloadsChart"></canvas>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th>Project</th>
                    <th>Ecosystem</th>
                    <th>Package Name</th>
                    <th>Version</th>
                    <th>Downloads</th>
                </tr>
            </thead>
            <tbody>
{table_rows}
            </tbody>
        </table>
    </div>

    <!-- Section 2: Partial Adoption Signals -->
    <div class="section">
        <h2>&#128200; Partial Adoption Signals</h2>
        <p class="description">
            These metrics provide adoption signals but may not be directly comparable or comprehensive.
        </p>
        
        <div class="caveat">
            <strong>&#9888;&#65039; Important:</strong> GitHub release asset downloads are per-asset and may be 
            counted differently across repositories. Docker dependent counts reflect packages that 
            depend on these images, not direct usage.
        </div>
        
        <h3>GitHub Release Asset Downloads</h3>
        <div class="chart-container">
            <canvas id="repoDownloadsChart"></canvas>
        </div>
        
        <div class="repo-list">
{repo_items}
        </div>
        
        <h3>Docker Dependent Packages</h3>
{docker_items}
        
        <h3>Comprehensive Provider Coverage</h3>
        <p class="description">
            Full list of ecosyste.ms-supported providers checked for each project:
        </p>
        
        <table>
            <thead>
                <tr>
                    <th>Project</th>
                    <th>Package Registries Found</th>
                    <th>Repository Hosts Found</th>
                </tr>
            </thead>
            <tbody>
{comprehensive_table_rows}
            </tbody>
        </table>
        
        <div class="caveat">
            <strong>Note:</strong> This shows which ecosyste.ms-supported providers have data for each project. 
            Empty cells mean no packages were found in that registry for the project name.
        </div>
    </div>

    <!-- Section 3: Not Covered -->
    <div class="section">
        <h2>&#10060; Not Covered by ecosyste.ms</h2>
        <p class="description">
            The following data sources exist but are not exposed through ecosyste.ms APIs:
        </p>
        
        <div class="not-covered">
            <ul>
                <li><strong>Docker Hub total pulls:</strong> Available via Docker Hub API but not aggregated in ecosyste.ms</li>
                <li><strong>download.owncloud.com tarball downloads:</strong> ownCloud's own download server statistics</li>
                <li><strong>PyPI download statistics:</strong> PyPI removed native download stats in 2018</li>
                <li><strong>Marketplace/extension downloads:</strong> ownCloud app marketplace statistics</li>
                <li><strong>Enterprise/on-premise deployments:</strong> Not trackable via public registries</li>
            </ul>
        </div>
        
        <p>
            <strong>Note:</strong> This page intentionally separates "real" download counters from 
            partial signals to avoid implying that the data presents a complete adoption picture. 
            The ecosyste.ms project aggregates data from many sources, but some important metrics 
            remain outside its scope.
        </p>
    </div>

    <script>
        const realDownloadsCtx = document.getElementById('realDownloadsChart').getContext('2d');
        const realDownloadsData = {real_downloads_sorted_json};
        
        const realValues = realDownloadsData.map(d => d.downloads || 0);
        
        new Chart(realDownloadsCtx, {{
            type: 'bar',
            data: {{
                labels: realDownloadsData.map(d => d.name + ' (' + d.ecosystem + ')'),
                datasets: [{{
                    label: 'Downloads',
                    data: realValues,
                    backgroundColor: '#3498db',
                    borderColor: '#2980b9',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            callback: function(value) {{
                                return value.toLocaleString();
                            }}
                        }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        display: false
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                return context.parsed.y.toLocaleString();
                            }}
                        }}
                    }}
                }}
            }}
        }});
        
        const repoDownloadsCtx = document.getElementById('repoDownloadsChart').getContext('2d');
        const repoDownloadsData = {repo_downloads_data_json};
        
        const allRepoSeries = [];
        const colorPalette = ['#e74c3c', '#3498db', '#2ecc71', '#9b59b6', '#f1c40f', '#1abc9c', '#d35400', '#34495e'];
        
        repoDownloadsData.forEach((repo, index) => {{
            const series = repo.time_series.map(r => ({{
                x: r.published_at || new Date().toISOString(),
                y: r.downloads || 0
            }})).reverse();
            
            allRepoSeries.push({{
                label: repo.repo,
                data: series,
                borderColor: colorPalette[index % colorPalette.length],
                backgroundColor: colorPalette[index % colorPalette.length] + '40',
                tension: 0.1,
                fill: false
            }});
        }});
        
        new Chart(repoDownloadsCtx, {{
            type: 'line',
            data: {{
                datasets: allRepoSeries
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{
                        type: 'time',
                        time: {{
                            unit: 'month',
                            displayFormats: {{
                                month: 'MMM YYYY'
                            }}
                        }},
                        title: {{
                            display: true,
                            text: 'Release Date'
                        }}
                    }},
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            callback: function(value) {{
                                return value.toLocaleString();
                            }}
                        }},
                        title: {{
                            display: true,
                            text: 'Downloads per Release'
                        }}
                    }}
                }},
                plugins: {{
                    legend: {{
                        position: 'right'
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                return context.dataset.label + ': ' + context.parsed.y.toLocaleString();
                            }}
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    
    with open(DOCS_DIR / "index.html", "w") as f:
        f.write(html)
    
    print(f"Generated report at {DOCS_DIR / 'index.html'}")


def main():
    """Main entry point."""
    print("Starting data fetch and report generation...")
    
    client = APIClient()
    
    package_data = fetch_package_data(client)
    repo_data = fetch_repo_data(client)
    docker_data = fetch_docker_data(client)
    
    comprehensive_data = {}
    for repo_name in OWNCLOUD_REPOS:
        base_name = repo_name.split("/")[-1] if "/" in repo_name else repo_name
        
        comprehensive_data[repo_name] = {
            "packages": fetch_comprehensive_package_data(client, base_name),
            "repos": fetch_repo_across_hosts(client, base_name),
        }
    
    save_raw_data(package_data, repo_data, docker_data, comprehensive_data)
    generate_html_report(package_data, repo_data, docker_data, comprehensive_data)
    
    print("\nData fetch and report generation complete!")
    print(f"Raw data cached in: {DATA_DIR}")
    print(f"Static site generated in: {DOCS_DIR}")


if __name__ == "__main__":
    main()
