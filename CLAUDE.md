# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Zenzefi Client is a Windows desktop application built with PySide6 that provides a local HTTPS proxy for connecting to the Zenzefi server. It acts as a man-in-the-middle proxy that rewrites URLs and handles both HTTP/HTTPS requests and WebSocket connections, allowing local development/testing against a remote server.

**Key Technology Stack:**
- Python 3.13 (strict version requirement)
- PySide6 (Qt for GUI)
- aiohttp (async HTTP server and client)
- Poetry for dependency management
- PyInstaller for building executables

## Development Commands

### Running the Application
```bash
# Development mode
python main.py

# The application will:
# - Create app_data/ directory for config, logs, and certificates
# - Generate self-signed SSL certificates if they don't exist
# - Start with system tray icon (can be configured to show window)
```

### Building Executable
```bash
# Build with PyInstaller (standard way)
pyinstaller ZenzefiClient.spec

# Build with optimization script (recommended)
python build_optimized.py

# Output will be in dist/ directory
# The spec file includes resource bundling and Windows-specific settings
```

**Optimized Build Script** (`build_optimized.py`):
- Automatically cleans previous builds and caches
- Compiles .pyc files with optimization level 2 (-OO flag)
- Runs PyInstaller with optimized parameters
- Displays build statistics (file sizes, file count)

### Managing Dependencies
```bash
# Install dependencies
poetry install

# Add new dependency
poetry add <package>

# Update dependencies
poetry update
```

## Architecture Overview

### Singleton Pattern Usage

The codebase extensively uses the singleton pattern for global state management. Key singletons:

- `ConfigManager` - via `get_config()` in `core/config_manager.py`
- `ProxyManager` - via `get_proxy_manager()` in `core/proxy_manager.py`
- `ProcessManager` - via `get_process_manager()` in `utils/process_manager.py`
- `ThemeManager` - via `get_theme_manager()` in `ui/theme_manager.py`
- `IconManager` - via `get_icon_manager()` in `ui/icons.py`

**Important:** Always use the getter functions to access these objects, never instantiate them directly.

### Proxy Architecture

**IMPORTANT:** The Desktop Client is a **simplified proxy** that forwards ALL requests to the Backend Server (127.0.0.1:8000). The Backend handles authentication, content rewriting, caching, and proxying to Zenzefi Server.

The core proxy functionality (`core/proxy_manager.py`) has two main classes:

1. **ZenzefiProxy**: Simple forwarding proxy
   - `handle_http()` - Forwards ALL HTTP/HTTPS requests to backend (127.0.0.1:8000)
   - `_proxy_to_backend()` - Core method that proxies requests to backend server
   - `router()` - Simple router that forwards all requests through `handle_http()`
   - `get_full_stats()` - Returns basic statistics (requests, responses, errors, active connections)

   **Cookie Forwarding:**
   - Forwards browser cookies to backend
   - Parses Set-Cookie headers from backend and re-sets them for local proxy domain (127.0.0.1:61000)
   - Uses `secure=False` for localhost with self-signed certificate
   - Sends `X-Local-Url` header to backend for proper content rewriting

   **Connection Management:**
   - TCPConnector configured for backend (ssl=False, localhost HTTP)
   - Connection pool: 100 total limit, 50 per host
   - DNS cache: 5 minutes TTL
   - Keep-alive: 60 seconds timeout
   - Semaphore limiting concurrent connections to 50

2. **ProxyManager**: Manages the proxy server lifecycle
   - Runs aiohttp server in a separate thread with its own event loop
   - Port conflict detection and resolution (can terminate processes blocking port 61000)
   - SSL context setup using self-signed certificates (for client connections)
   - Thread-safe start/stop operations using `asyncio.run_coroutine_threadsafe()`
   - **Graceful shutdown:** Properly cleans up session, connector, runner, and site resources
   - Logs basic statistics on shutdown
   - `get_proxy_stats()` - Retrieves real-time performance statistics

**Critical Details:**
- Desktop Client does **NOT** do content rewriting, caching, compression, or WebSocket handling
- ALL requests are forwarded to Backend Server at http://127.0.0.1:8000
- Backend adds `/api/v1/proxy` prefix when routing: browser sees clean URLs, backend gets prefixed paths
- Desktop Client's `local_url` is WITHOUT prefix: `https://127.0.0.1:61000` (clean URL for browser)
- Backend receives requests with prefix: `http://127.0.0.1:8000/api/v1/proxy{path}`
- Connection pool is for backend communication only (HTTP, not HTTPS)
- Backend is responsible for: authentication, content rewriting, caching, compression, proxying to Zenzefi

**Note:** Desktop Client does NOT have CacheManager or ContentRewriter modules. These features are implemented ONLY in the Backend Server:
- Backend's `app/services/content_rewriter.py` - URL rewriting in HTML/CSS/JS
- Backend's caching logic - LRU cache for static resources
- Desktop Client simply forwards requests/responses without modification

### Authentication Architecture

The application uses a **cookie-based authentication system** with integration to a backend server:

**Architecture Flow:**
1. **Browser** → Desktop Client Proxy (https://127.0.0.1:61000)
2. **Desktop Client Proxy** → Backend Server (http://127.0.0.1:8000)
3. **Backend Server** → Zenzefi Server (https://zenzefi.melxiory.ru)

**Key Components:**

1. **Access Token Requirement** (Desktop Client)
   - Desktop client **requires** access token before starting proxy
   - Token is stored encrypted in `ConfigManager` using Fernet encryption
   - User must configure token in main window before starting proxy
   - Attempting to start proxy without token shows error message
   - `config.has_access_token()` checks if token is configured

2. **Authentication Flow:**
   ```
   1. User configures access token in Desktop Client
   2. User clicks "Start Proxy" (or "Open in Browser")
   3. Desktop Client validates token is present
   4. Proxy starts on https://127.0.0.1:61000
   5. Browser automatically opens: https://127.0.0.1:61000/api/v1/proxy?token=xyz
   6. Desktop Client forwards request to backend: http://127.0.0.1:8000/api/v1/proxy?token=xyz
   7. Backend shows auth page or validates cookie
   8. JavaScript sends token to /api/v1/proxy/authenticate
   9. Backend validates token, sets `zenzefi_access_token` cookie
   10. Browser redirected to /api/v1/proxy/ (now authenticated via cookie)
   11. All subsequent requests include cookie, forwarded by Desktop Client to backend
   ```

3. **Cookie Forwarding** (Desktop Client → Backend):
   - Desktop Client reads cookies from browser request
   - Forwards cookies to backend in request
   - Backend returns Set-Cookie headers
   - Desktop Client parses Set-Cookie and re-sets for local domain (127.0.0.1:61000)
   - Uses `secure=False` for localhost with self-signed certificate

4. **Auth Endpoints** (ALL handled by Backend):
   - `/api/v1/proxy/authenticate` - Token → Cookie exchange
   - `/api/v1/proxy/status` - Check authentication status
   - `/api/v1/proxy/logout` - Clear authentication cookie
   - Desktop Client simply forwards these requests to backend

5. **Browser Auto-Open:**
   - When proxy starts, Desktop Client automatically opens browser
   - URL: `https://127.0.0.1:61000/api/v1/proxy?token={encrypted_token}`
   - This initiates cookie authentication flow
   - Implemented in `TrayIcon.start_nginx()` and main window

**IMPORTANT:** The backend server must be running at `http://127.0.0.1:8000` for authentication to work. Start with: `poetry run uvicorn app.main:app --reload`

### Threading Model

**Main Thread:** Qt GUI event loop
**Proxy Thread:** Separate thread running asyncio event loop for aiohttp server
**ProxyManagerThread (QThread):** Bridges GUI and ProxyManager for non-blocking operations

When modifying proxy operations:
- Use `asyncio.run_coroutine_threadsafe()` to schedule coroutines in the proxy's event loop
- Never call `asyncio.run()` while the proxy loop is running
- All proxy start/stop operations go through ProxyManagerThread to avoid blocking the GUI

### Configuration System

Configuration is stored in JSON format at:
- **Dev mode:** `app_data/config.json` (relative to project root)
- **Portable mode:** `%LOCALAPPDATA%\Zenzefi\config.json` (Windows)

The `ConfigManager` supports dot notation for nested keys:
```python
config.get('proxy.local_port')  # Returns 61000
config.set('application.theme', 'dark', save=True)
```

Config is auto-merged with defaults, so missing keys always have fallback values.

### Single Instance Enforcement

The application uses platform-specific mechanisms to ensure only one instance runs:
- Windows: Named mutex (`utils/single_instance_windows.py`)
- Fallback: File-based locking (`utils/single_instance_file.py`)

The lock is acquired in `main()` before QApplication creation and released in the `cleanup()` handler connected to `app.aboutToQuit`.

### Certificate Management

Self-signed certificates are auto-generated on first run using the cryptography library:
- Certificates stored in `app_data/certificates/` (or `%LOCALAPPDATA%\Zenzefi\certificates\`)
- Valid for localhost and 127.0.0.1 with SAN (Subject Alternative Name)
- 2048-bit RSA keys, SHA256 signature, 365-day validity

The application will refuse to start if certificate generation fails.

### Logging

Logging is configured early in `main.py` before any imports with automatic rotation:
- **File:** `app_data/logs/zenzefi_client.log` (UTF-8 encoded)
- **Rotation:** `RotatingFileHandler` with 5MB max size, 5 backup files
- **Console:** stdout
- **GUI:** Custom `LogHandler` with debouncing (200ms batching) emits signals to `QTextEdit` in MainWindow

All modules use `logging.getLogger(__name__)` pattern.

**Performance optimization:** GUI log handler buffers messages for 200ms and sends them in batches to reduce UI thread overhead.

## UI and Theming

The application uses a Mercedes-Benz inspired dark theme by default with a light theme option. Themes are defined in:
- `ui/theme_manager.py` - Theme switching and stylesheet generation
- `ui/colors.py` - Color palette definitions
- `ui/styles.py` - Additional style helpers

**Theme switching:** Changes are saved to config and require restarting the app or manually calling `apply_theme()` on all windows.

### System Tray

The tray icon (`ui/tray_icon.py`) is always visible and provides:
- Show/hide main window (lazy loaded on first open)
- Quick start/stop proxy
- Exit application

**Lazy Loading:** The main window (`MainWindow`) is created on-demand:
- If `start_minimized=false`: created at startup
- If `start_minimized=true`: created only when user opens it from tray
- This saves ~20-30MB RAM when running minimized

The main window can be closed while keeping the app running in the tray (controlled by `minimize_to_tray` config).

## Port Management

Port 61000 is hardcoded as the local proxy port. The `ProxyManager` includes sophisticated port conflict handling:

1. Checks if port is available
2. If blocked, checks if it's our own process (zombie instance)
3. Attempts to terminate the blocking process (requires admin rights for non-owned processes)
4. Provides clear error messages based on admin status

Admin detection uses `ctypes.windll.shell32.IsUserAnAdmin()` on Windows.

## PyInstaller Packaging

The `ZenzefiClient.spec` file configures:
- Single-file executable (`onefile=True` equivalent via script collecting)
- Resource bundling from `resources/` directory
- No console window (`console=False`)
- Windows icon and version info
- UPX compression enabled (30-50% size reduction)
- Strip disabled on Windows (requires GNU binutils, not available)

**Critical module exclusions:**
- Most unused libraries are excluded to reduce size (tkinter, matplotlib, numpy, pandas, etc.)
- **DO NOT exclude:** `email`, `html`, `xml.etree` - required by `cryptography` and `aiohttp`
- Excluding these will cause runtime errors: "No module named 'email'" during certificate generation

**Resources access:** In frozen mode, resources are accessed via PyInstaller's temp directory mechanism. The `get_app_data_dir()` function handles path resolution for both dev and frozen modes.

**Build warnings:** "Failed to run strip" warnings on Windows are normal and harmless - strip is a Unix-only tool.

## Important Patterns

### Async/Sync Bridge Pattern
When the GUI needs to trigger async operations:
```python
# In ProxyManagerThread
def run(self):
    if self.action == "start":
        self.proxy_manager.start(61000, remote_url)
    # start() internally creates thread + event loop
```

### Error Handling
- Critical errors show QMessageBox and are logged
- Port conflicts include actionable user instructions
- Global exception handler in `setup_exception_handler()` catches unhandled exceptions

### Resource Paths
Always use `get_app_data_dir()` from `core/config_manager.py` for data files. Never use hardcoded paths.

## Known Constraints

- **Python Version:** Locked to 3.13.x (check `pyproject.toml`)
- **Port:** Hardcoded to 61000 (changing requires updating both proxy manager and content rewriting)
- **Platform:** Primarily Windows (uses Windows-specific admin checks and mutex)
- **Single Instance:** The app enforces single instance - attempting to launch again shows a message
- **Certificate Trust:** Users must manually trust the self-signed certificate in their browser

## Startup and Initialization

The application implements a sophisticated async startup process for responsive UI:

### Splash Screen (`ui/splash_screen.py`)
- Mercedes-Benz themed splash screen with progress bar
- Shows during async initialization (certificates, proxy setup, port checks)
- Theme-aware: adapts to dark/light theme from config
- Progress updates: 10% → 40% → 70% → 100% with descriptive messages

### Async Initialization (`core/startup_manager.py`)
- **StartupThread** (QThread) runs initialization in background
- **Progress signals** update splash screen without blocking
- **Initialization steps:**
  1. SSL certificate validation (10-40%)
  2. ProxyManager initialization (40-70%)
  3. Port availability checks (70-80%)
  4. Configuration loading (80-100%)
- **Qt event processing:** Main loop actively processes events during `thread.wait()` to handle signals immediately
- **Error handling:** Failures captured and returned via `finished_signal` with error messages

### Critical Startup Pattern
```python
# In main.py - proper Qt signal handling
while startup_thread.isRunning():
    app.processEvents()  # Process Qt signals immediately
    startup_thread.wait(10)  # Wait 10ms
app.processEvents()  # Final pass to catch any late signals
```

This pattern ensures Qt signals are processed during thread execution, preventing race conditions where `finished_signal` arrives but isn't processed before checking results.

## Performance and Memory Management

The application includes several optimizations for production use:

### Desktop Client Performance
**Important:** Desktop Client is a simple forwarding proxy. All content processing optimizations (caching, compression, rewriting) are handled by the Backend Server.

Desktop Client optimizations:
- **Connection pooling** to backend via `aiohttp.TCPConnector` (100 total, 50/host)
- **Keep-alive** connections to backend (60s timeout) - reduces connection overhead
- **DNS caching** for backend lookups (5 min TTL)
- **Concurrency limits** - Semaphore caps concurrent backend connections at 50
- **Basic statistics** - Tracks requests, responses, errors, active connections

### Memory Management
- **Log rotation** - `RotatingFileHandler` at 5MB, keeps 5 backups, prevents disk space issues
- **Lazy loading** - MainWindow created on-demand when user opens it, saves 20-30MB when minimized to tray
- **Minimal state** - Desktop Client maintains minimal state, all processing in Backend

### GUI Performance
- **Log debouncing** - `LogHandler` batches messages for 200ms, reduces UI updates by 80-90%
- **Lazy window creation** - MainWindow and its components loaded only when user requests
- **Async operations** - All proxy operations run in separate thread/event loop, never block Qt GUI
- **QTimer for theme** - Theme application deferred via `QTimer.singleShot(0)` to prioritize window rendering

### Backend Performance (Separate Server)
**Note:** These optimizations are in the Backend Server, not Desktop Client:

- **LRU cache** for static resources - reduces repeated processing
- **Content rewriting cache** - MD5-based caching of rewritten content
- **Precompiled regex** patterns for faster URL rewriting
- **Compression** - gzip/deflate for text responses (configurable)
- **Streaming** - Large file streaming to reduce memory usage
- **WebSocket handling** - Bidirectional proxying with size limits

### Statistics and Monitoring
Desktop Client collects basic metrics (no overhead):
- Request/response counts
- Active connections
- Error rates
- Logged on shutdown

Backend Server collects detailed performance metrics:
- Cache hit/miss rates
- Compression statistics
- Content rewriting performance
- WebSocket connections

## Development Notes

- The app uses Russian language strings in UI and logs
- Color scheme values are defined in `ui/colors.py` as `COLORS` (dark) and `COLORS_LIGHT`
- Process termination logic in `utils/process_manager.py` requires careful testing as it can kill processes
- Desktop Client is intentionally simplified - all complex logic is in Backend Server
- Basic statistics are logged on proxy shutdown for monitoring
- Access token is stored encrypted using Fernet (symmetric encryption)
- Backend must be running for Desktop Client to function properly
