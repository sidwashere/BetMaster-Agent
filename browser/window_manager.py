"""
browser/window_manager.py
Detects and manages the 1xbet browser window using pywinctl/win32gui
"""

import logging
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    import pywinctl as pwc
    PYWINCTL_AVAILABLE = True
except ImportError:
    PYWINCTL_AVAILABLE = False
    logger.warning("pywinctl not available, using fallback")

try:
    import win32gui
    import win32process
    import psutil
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False


@dataclass
class BrowserWindow:
    """Represents a detected browser window"""
    hwnd: int
    title: str
    process_name: str
    pid: int
    is_active: bool = False


class WindowManager:
    """
    Manages browser window detection and focus.
    Finds and attaches to existing 1xbet browser windows.
    """
    
    # Keywords to identify 1xbet windows
    XBET_TERMS = ["1xbet", "1xbet.com", "1XBET"]
    
    # Supported browsers
    BROWSER_PROCESSES = ["chrome", "msedge", "firefox", "brave", "opera"]
    
    def __init__(self):
        self._cached_window: Optional[BrowserWindow] = None
        self._last_scan_time = 0
        self._scan_cache_ttl = 5  # seconds
    
    def find_1xbet_window(self, force_refresh: bool = False) -> Optional[BrowserWindow]:
        """
        Find the 1xbet browser window.
        Uses caching to avoid excessive system calls.
        """
        current_time = time.time()
        
        # Return cached result if still valid
        if not force_refresh and self._cached_window and (current_time - self._last_scan_time) < self._scan_cache_ttl:
            return self._cached_window
        
        window = self._find_window_internal()
        
        if window:
            self._cached_window = window
            self._last_scan_time = current_time
            logger.info(f"Found 1xbet window: {window.title} (PID: {window.pid})")
        else:
            logger.warning("No 1xbet window found")
        
        return window
    
    def _find_window_internal(self) -> Optional[BrowserWindow]:
        """Internal method to find the 1xbet window"""
        
        if PYWINCTL_AVAILABLE:
            return self._find_with_pywinctl()
        elif WIN32_AVAILABLE:
            return self._find_with_win32gui()
        else:
            return self._find_fallback()
    
    def _find_with_pywinctl(self) -> Optional[BrowserWindow]:
        """Find window using pywinctl"""
        try:
            # Get all windows
            all_windows = pwc.getAllWindows()
            
            for window in all_windows:
                try:
                    title = window.title.lower()
                    # Check if title contains 1xbet
                    if any(term in title for term in self.XBET_TERMS):
                        # Get process info
                        try:
                            pid = window.getProcessID()
                            proc = psutil.Process(pid)
                            proc_name = proc.name().lower()
                        except:
                            proc_name = "unknown"
                        
                        return BrowserWindow(
                            hwnd=window._hWnd,
                            title=window.title,
                            process_name=proc_name,
                            pid=pid,
                            is_active=window.isActive
                        )
                except Exception as e:
                    continue
            
            return None
        except Exception as e:
            logger.error(f"pywinctl search error: {e}")
            return None
    
    def _find_with_win32gui(self) -> Optional[BrowserWindow]:
        """Find window using win32gui (fallback)"""
        try:
            result = {"window": None}
            
            def enum_callback(hwnd, windows):
                if win32gui.IsWindowVisible(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if any(term in title.lower() for term in self.XBET_TERMS):
                        # Get process ID
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        
                        # Get process name
                        try:
                            proc = psutil.Process(pid)
                            proc_name = proc.name().lower()
                        except:
                            proc_name = "unknown"
                        
                        result["window"] = BrowserWindow(
                            hwnd=hwnd,
                            title=title,
                            process_name=proc_name,
                            pid=pid,
                            is_active=True
                        )
                        return False  # Stop enumeration
                return True
            
            win32gui.EnumWindows(enum_callback, None)
            return result["window"]
        except Exception as e:
            logger.error(f"win32gui search error: {e}")
            return None
    
    def _find_fallback(self) -> Optional[BrowserWindow]:
        """Last resort - return None and let caller handle"""
        logger.warning("No window detection method available")
        return None
    
    def bring_to_front(self, window: BrowserWindow) -> bool:
        """Bring the 1xbet window to foreground"""
        try:
            if PYWINCTL_AVAILABLE:
                # Find the window object again
                all_windows = pwc.getAllWindows()
                for w in all_windows:
                    if w._hWnd == window.hwnd:
                        w.activate()
                        return True
            
            elif WIN32_AVAILABLE:
                win32gui.SetForegroundWindow(window.hwnd)
                return True
            
            return False
        except Exception as e:
            logger.error(f"Failed to bring window to front: {e}")
            return False
    
    def is_window_valid(self, window: BrowserWindow) -> bool:
        """Check if the window is still valid/open"""
        try:
            if WIN32_AVAILABLE:
                return win32gui.IsWindow(window.hwnd)
            elif PYWINCTL_AVAILABLE:
                all_windows = pwc.getAllWindows()
                return any(w._hWnd == window.hwnd for w in all_windows)
            return False
        except:
            return False
    
    def get_active_window_title(self) -> Optional[str]:
        """Get the currently active/focused window title"""
        try:
            if PYWINCTL_AVAILABLE:
                active = pwc.getActiveWindow()
                if active:
                    return active.title
            elif WIN32_AVAILABLE:
                hwnd = win32gui.GetForegroundWindow()
                return win32gui.GetWindowText(hwnd)
        except Exception as e:
            logger.debug(f"Get active window error: {e}")
        return None
    
    def is_1xbet_active(self) -> bool:
        """Check if 1xbet window is currently active/focused"""
        active_title = self.get_active_window_title()
        if active_title:
            return any(term in active_title.lower() for term in self.XBET_TERMS)
        return False
    
    def get_chrome_debug_port(self, window: BrowserWindow) -> Optional[str]:
        """
        Get Chrome DevTools Protocol port for the browser window.
        This allows connecting via Playwright CDP.
        """
        try:
            # Chrome remote debugging port is usually 9222
            # For existing window, we need to find the actual port
            # This is typically stored in the environment or can be discovered
            
            # Common approach: check if chrome was started with --remote-debugging-port
            # We'll try to connect to common ports
            proc = psutil.Process(window.pid)
            
            # Get command line to check for debugging port
            try:
                cmdline = proc.cmdline()
                for arg in cmdline:
                    if "--remote-debugging-port=" in arg:
                        port = arg.split("=")[1]
                        logger.info(f"Found Chrome debug port: {port}")
                        return f"localhost:{port}"
            except:
                pass
            
            # Default port fallback
            return "localhost:9222"
            
        except Exception as e:
            logger.debug(f"Could not get debug port: {e}")
            return "localhost:9222"
    
    def list_all_browsers(self) -> List[Dict[str, Any]]:
        """List all browser windows (useful for debugging)"""
        browsers = []
        
        try:
            if PYWINCTL_AVAILABLE:
                all_windows = pwc.getAllWindows()
                for w in all_windows:
                    try:
                        title = w.title.lower()
                        # Check if it's a browser
                        pid = w.getProcessID()
                        proc = psutil.Process(pid)
                        proc_name = proc.name().lower()
                        
                        if any(b in proc_name for b in self.BROWSER_PROCESSES):
                            browsers.append({
                                "title": w.title,
                                "process": proc_name,
                                "pid": pid,
                                "hwnd": w._hWnd,
                                "is_1xbet": any(term in title for term in self.XBET_TERMS)
                            })
                    except:
                        continue
        except Exception as e:
            logger.error(f"Error listing browsers: {e}")
        
        return browsers


# Singleton instance
_window_manager: Optional[WindowManager] = None

def get_window_manager() -> WindowManager:
    """Get the global window manager instance"""
    global _window_manager
    if _window_manager is None:
        _window_manager = WindowManager()
    return _window_manager
