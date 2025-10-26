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
# Build with PyInstaller
pyinstaller ZenzefiClient.spec

# Output will be in dist/ directory
# The spec file includes resource bundling and Windows-specific settings
```

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

The core proxy functionality (`core/proxy_manager.py`) has three main classes:

1. **LRUCache**: In-memory cache for static resources
   - Implements Least Recently Used eviction policy
   - Default capacity: 100 items
   - Tracks hits/misses for performance monitoring
   - Used for both HTTP responses and `fix_content()` results
   - Thread-safe OrderedDict implementation

2. **ZenzefiProxy**: Handles the actual proxying logic
   - `handle_http()` - Proxies HTTP/HTTPS requests with caching, streaming, compression, and header rewriting
   - `handle_websocket()` - Bidirectional WebSocket proxying with size limits (10MB)
   - `fix_content()` - Rewrites URLs in HTML/CSS/JS with regex caching
   - `router()` - Routes between HTTP and WebSocket handlers based on Upgrade header
   - **Performance features:**
     - LRU cache for static resources (CSS, JS, images, fonts)
     - Streaming for files >1MB to reduce memory usage
     - Precompiled regex patterns for faster URL rewriting
     - Content rewriting cache with MD5 hashing
     - Connection semaphore limiting concurrent connections to 50
     - **gzip/deflate compression** for text responses (level 6, >1KB threshold)
     - **Keep-alive optimization** with explicit timeout headers (60s, 100 requests)
     - **Performance statistics** tracking requests, responses, compression ratio, cache hits
   - `_compress_content()` - Automatic response compression based on Accept-Encoding
   - `_is_compressible()` - Detects text-based content types suitable for compression
   - `get_full_stats()` - Returns detailed performance metrics

3. **ProxyManager**: Manages the proxy server lifecycle
   - Runs aiohttp server in a separate thread with its own event loop
   - Port conflict detection and resolution (can terminate processes blocking port 61000)
   - SSL context setup using self-signed certificates
   - Thread-safe start/stop operations using `asyncio.run_coroutine_threadsafe()`
   - **Connection pooling:** TCPConnector with 100 connection limit, 30 per host, DNS caching (5 min TTL)
   - **Graceful shutdown:** Properly cleans up session, connector, runner, and site resources
   - Logs cache statistics and performance metrics on shutdown
   - `get_proxy_stats()` - Retrieves real-time performance statistics

**Critical Details:**
- The proxy rewrites all references to `https://zenzefi.melxiory.ru` → `https://127.0.0.1:61000` in responses, including WebSocket URLs (`wss://`)
- Static resources are cached in memory for faster repeated requests
- Large files (>1MB) are streamed to avoid loading entirely into memory
- Connection pool is reused across requests to reduce SSL handshake overhead
- **Automatic compression** saves 50-80% bandwidth for text responses (HTML, CSS, JS, JSON)
- **HTTP/2 ready** - TCPConnector configured to support HTTP/2 when available
- Statistics collection is always active in background for monitoring

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

### Proxy Performance
- **LRU cache** for static resources (100 items max) - reduces repeated requests processing
- **Connection pooling** via `aiohttp.TCPConnector` (100 total, 30/host) - reuses SSL connections, DNS caching (5min)
- **Streaming** for large files (>1MB threshold) - avoids memory spikes, 8KB chunks
- **Precompiled regex** patterns in `ZenzefiProxy` - faster URL rewriting
- **Content rewriting cache** - MD5-based caching of `fix_content()` results (max 100KB/file)
- **Concurrency limits** - Semaphore caps connections at 50 to prevent resource exhaustion
- **gzip/deflate compression** - Automatic text response compression (level 6), saves 50-80% bandwidth
- **Keep-alive optimization** - Explicit headers (timeout=60s, max=100 requests) reduce connection overhead
- **HTTP/2 ready** - TCPConnector configured to use HTTP/2 when supported by upstream

### Network Optimizations
- **Compression:** Only compresses content >1KB to avoid overhead on small responses
- **Keep-alive:** Connection reuse reduces SSL handshake latency by ~200-500ms per request
- **DNS caching:** 5-minute TTL prevents repeated DNS lookups
- **Connection pooling:** Up to 30 persistent connections per host

### Memory Management
- **Log rotation** - `RotatingFileHandler` at 5MB, keeps 5 backups, prevents disk space issues
- **Lazy loading** - MainWindow created on-demand when user opens it, saves 20-30MB when minimized to tray
- **Cache size limits** - LRU eviction policy prevents unbounded memory growth, max 100 cached items
- **WebSocket limits** - 10MB max message size prevents memory attacks
- **Streaming** - Large responses streamed in 8KB chunks, never fully loaded into memory
- **Regex caching** - `fix_content()` caches results for repeated identical content

### GUI Performance
- **Log debouncing** - `LogHandler` batches messages for 200ms, reduces UI updates by 80-90%
- **Lazy window creation** - MainWindow and its components loaded only when user requests
- **Async operations** - All proxy operations run in separate thread/event loop, never block Qt GUI
- **QTimer for theme** - Theme application deferred via `QTimer.singleShot(0)` to prioritize window rendering

### Statistics and Monitoring
The proxy collects performance metrics in background (no UI overhead):
- Request/response counts, active connections, error rates
- Cache hit/miss rates, cache size
- Compression statistics: responses compressed, bytes saved
- Streaming usage for large files
- Logged on shutdown for performance analysis

## Development Notes

- The app uses Russian language strings in UI and logs
- Color scheme values are defined in `ui/colors.py` as `COLORS` (dark) and `COLORS_LIGHT`
- Process termination logic in `utils/process_manager.py` requires careful testing as it can kill processes
- WebSocket proxying maintains two concurrent tasks (client→server, server→client) using `asyncio.gather()`
- Cache statistics are logged on proxy shutdown for monitoring performance
