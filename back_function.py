import os, platform, json, shutil, time, re, zipfile, piexif, logging, random
import queue, hashlib, threading, bisect, subprocess
from datetime import datetime
from pathlib import Path
from typing import Iterable, Tuple, List, Dict, Any
from collections import deque
from fractions import Fraction

# External libraries
from mutagen import File
from pymediainfo import MediaInfo
from PyPDF2 import PdfReader
from PIL import Image
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from xml.etree import ElementTree

# Local import
from main import get_config_path

# --- CROSS-PLATFORM SETUP ---
IS_WINDOWS = platform.system() == "Windows"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes
    import send2trash
else:
    # Linux/Mac placeholders
    win32gui = None
    win32con = None
    wintypes = None
    ctypes = None
    # Try to import send2trash for Linux trash support
    try:
        from send2trash import send2trash
    except ImportError:
        send2trash = None

#region Opening a folder

def open_folder(folder):
    """Returns a list of all files (their paths) in a selected folder"""
    if folder:
        folderList = [] 
        for root, dirs, files in os.walk(folder): 
            for file in files:
                file_path = os.path.join(root, file)
                folderList.append(file_path)
        return folderList

#region get many file info

def get_file_info(file_path):
    """Returns a dictionary containing properties of a selected file"""
    if file_path:
        fileDict = {}
        try:
            fileDict['Full Name'] = os.path.basename(file_path)
            fileDict['Name'] = os.path.splitext(os.path.basename(file_path))[0]
            fileDict['Extension'] = os.path.splitext(file_path)[1]
            fileDict['Directory'] = os.path.dirname(file_path)
            fileDict['Path'] = file_path
            stats = os.stat(file_path) 
            fileDict['Size'] = format_size(stats.st_size)
            
            # Cross-platform creation time
            if IS_WINDOWS:
                fileDict['Created'] = datetime.fromtimestamp(stats.st_birthtime).strftime('%d-%m-%Y')
            else:
                # Linux often doesn't give birthtime, use ctime (metadata change) or mtime
                try:
                    fileDict['Created'] = datetime.fromtimestamp(stats.st_birthtime).strftime('%d-%m-%Y')
                except AttributeError:
                    fileDict['Created'] = datetime.fromtimestamp(stats.st_ctime).strftime('%d-%m-%Y')

            fileDict['Modified'] = datetime.fromtimestamp(stats.st_mtime).strftime('%d-%m-%Y')
            fileDict['Accessed'] = datetime.fromtimestamp(stats.st_atime).strftime('%d-%m-%Y')

            # Metadata extraction (Cross-platform)
            audio_formats = ['.ogg', '.mp3', '.flac', '.wav']
            video_formats = ['.mp4', '.avi', '.mov', '.mkv','.flv']
            image_formats = ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.avif']
            
            if fileDict['Extension'] in audio_formats:
                fileDict.update({'Length (min)': None, 'Bitrate (kbps)': None,'Sample rate (Hz)': None,
                                'Channels': None, 'Mode': None,'Bit Depth': None})
                try:
                    audio = File(fileDict['Path'])
                    mode_map = {0: "Stereo", 1: "Joint stereo", 2: "Dual channel", 3: "Mono"}
                    if hasattr(audio, 'info'):
                        fileDict['Length (min)'] = round(number=float(audio.info.length/60), ndigits=2)
                        fileDict['Bitrate (kbps)'] = float(audio.info.bitrate/1000)
                        fileDict['Sample rate (Hz)'] = float(audio.info.sample_rate)
                        fileDict['Channels'] = int(audio.info.channels)
                        # Specific handling for mutagen types
                        if hasattr(audio.info, 'mode'):
                            fileDict['Mode'] = f'{mode_map.get(audio.info.mode, "Unknown")}'
                        if hasattr(audio.info, 'bits_per_sample'):
                            fileDict['Bit Depth'] = f'{audio.info.bits_per_sample}'
                except Exception:
                    pass

            if fileDict['Extension'] in video_formats:
                fileDict.update({'Length (min)': None, 'Bitrate (kbps)': None,'Framerate': None,
                                'Resolution': None, 'Aspect Ratio': None, 'Codec': None,
                                'Audio Codec': None, 'Channels': None})
                try:
                    media_info = MediaInfo.parse(file_path)
                    for track in media_info.tracks:
                        width = getattr(track, "width", None)
                        height = getattr(track, "height", None)
                        par = getattr(track, "pixel_aspect_ratio", 1.0)
                        ratio = Fraction(1, 1)
                        if width and height:
                            decimal_ar = float(width) / float(height) * float(par)
                            ratio = Fraction(decimal_ar).limit_denominator(100)

                        if track.track_type == "Video":
                            if track.duration:
                                fileDict['Length (min)'] = round(number=float(track.duration / 60000), ndigits=2)
                            if track.bit_rate:
                                fileDict['Bitrate (kbps)'] = float(track.bit_rate/1000)
                            if track.frame_rate:
                                fileDict['Framerate'] = float(track.frame_rate)
                            fileDict['Resolution'] = f'{track.width}x{track.height}'
                            fileDict['Aspect Ratio'] = f"{ratio.numerator}:{ratio.denominator}"
                            fileDict['Codec'] = track.format
                        elif track.track_type == "Audio":
                            fileDict['Audio Codec'] = track.format
                            fileDict['Channels'] = track.channel_s
                except Exception:
                    pass
            
            if fileDict['Extension'] in image_formats:
                def convert_to_degrees(value):
                    try:
                        d = value[0][0] / value[0][1]
                        m = value[1][0] / value[1][1]
                        s = value[2][0] / value[2][1]
                        return d + (m / 60.0) + (s / 3600.0)
                    except Exception:
                        return None
                
                fileDict.update({
                    'Resolution': None, 'Aspect Ratio': None, 'Bit Depth': None, 'Color Space': None,
                    'Compression': None, 'GPS Latitude': None, 'GPS Longitude': None
                })

                try:
                    media_info = MediaInfo.parse(file_path)
                    for track in media_info.tracks:
                        if track.track_type == "Image":
                            fileDict['Resolution'] = f"{track.width}x{track.height}" if track.width and track.height else None
                            if track.width and track.height:
                                ar = Fraction(track.width / track.height).limit_denominator(100)
                                fileDict['Aspect Ratio'] = f"{ar.numerator}:{ar.denominator}"
                            fileDict['Bit Depth'] = getattr(track, "bit_depth", None)
                            fileDict['Color Space'] = getattr(track, "color_space", None)
                            fileDict['Compression'] = getattr(track, "compression_mode", None)
                    
                    exif_dict = piexif.load(file_path)
                    gps = exif_dict.get("GPS", {})

                    def get_tag(tagset, key):
                        if key in tagset: return tagset[key]
                        return None
                    
                    gps_lat = get_tag(gps, piexif.GPSIFD.GPSLatitude)
                    gps_lat_ref = get_tag(gps, piexif.GPSIFD.GPSLatitudeRef)
                    gps_lon = get_tag(gps, piexif.GPSIFD.GPSLongitude)
                    gps_lon_ref = get_tag(gps, piexif.GPSIFD.GPSLongitudeRef)

                    if gps_lat and gps_lat_ref and gps_lon and gps_lon_ref:
                        lat = convert_to_degrees(gps_lat)
                        lon = convert_to_degrees(gps_lon)
                        if gps_lat_ref.decode() != "N": lat = -lat
                        if gps_lon_ref.decode() != "E": lon = -lon
                        fileDict['GPS Latitude'] = lat
                        fileDict['GPS Longitude'] = lon
                except Exception:
                    pass

        except Exception as e:
            pass
            
    return fileDict

def format_size(bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} PB"

#region system security:

def is_drive_root(path):
    abs_path = os.path.abspath(path)
    if IS_WINDOWS:
        drive, path_rest = os.path.splitdrive(abs_path)
        return drive != '' and abs_path.lower() == drive.lower() + os.sep
    else:
        return abs_path == os.sep 
    return False

def is_system_path_prohibited(path):
    try:
        abs_path = os.path.abspath(path)
    except ValueError:
        return True

    if IS_WINDOWS:
        SUBDIR_BLOCKS = [
            'c:\\windows', 'c:\\program files', 'c:\\program files (x86)',
            'c:\\programdata', os.path.expanduser('~') + os.sep + 'appdata'
        ]
        abs_path_norm = abs_path.lower()
    else:
        # Linux prohibited paths
        SUBDIR_BLOCKS = [
            '/bin', '/sbin', '/usr/bin', '/usr/sbin', '/etc',
            '/dev', '/proc', '/sys', '/root', '/boot'
        ]
        abs_path_norm = abs_path

    if is_drive_root(path):
        return True
        
    for system_path in SUBDIR_BLOCKS:
        if IS_WINDOWS:
             sys_path_norm = os.path.abspath(system_path).lower()
        else:
             sys_path_norm = os.path.abspath(system_path)

        if abs_path_norm.startswith(sys_path_norm):
            return True
            
    return False

#region Moving by criteria

def StartSorting(folder_structure, source_folder, groups, fileDicts):
    absolute_file_paths = []
    for dirpath, dirnames, filenames in os.walk(source_folder):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            absolute_file_paths.append(full_path)

    file_metadata_map = {d.get('Path'): d for d in fileDicts if d.get('Path')}

    def moveFiles(file_path):
        try:
            shutil.move(src=file_path, dst=f'{destination_folder}/{os.path.basename(file_path)}')
        except Exception as e:
            pass

    Folder_create_function(folder_structure) 
    
    for group in groups:
        destination_folder = group['destination']
        criteria = group['criteria']

        for file in absolute_file_paths:
            if not os.path.exists(file):
                continue
            file_data = file_metadata_map.get(file)
            matches_all_criteria = True

            for criterion in criteria:
                field = criterion['field']
                operator = criterion['operator']
                value = criterion['value']

                is_criterion_met = False

                if field == 'Extension':
                    file_extension = os.path.splitext(file)[1]
                    if operator == 'equals':
                        if file_extension.lower() == value.lower():
                            is_criterion_met = True

                elif field == 'Name':
                    filename = os.path.basename(file)
                    if operator == 'equals':
                        if filename == value: is_criterion_met = True
                    elif operator == 'contains':
                        if value in filename: is_criterion_met = True
                            
                elif field == 'Size':
                    unit_multipliers = {'B': 1,'KB': 1024,'MB': 1024 * 1024,'GB': 1024 * 1024 * 1024}
                    if isinstance(value, list) and len(value) == 2:
                        try:
                            size_value = float(value[0])
                            unit = value[1].upper()
                            stats = os.stat(file)
                            sizeBytes = stats.st_size
                            multiplier = unit_multipliers.get(unit, 1)
                            required_bytes = size_value * multiplier
                            if operator == 'greater than':
                                if sizeBytes > required_bytes: is_criterion_met = True
                            elif operator == 'less than':
                                if sizeBytes < required_bytes: is_criterion_met = True   
                        except (ValueError, FileNotFoundError, AttributeError):
                            pass
                            
                elif field in ['Color Space', 'Resolution', 'Aspect Ratio', 'Codec', 'Audio Codec', 'Compression', 'Mode']:
                    if file_data is not None:
                        actual_value = file_data.get(field)
                        if actual_value is not None and operator == 'equals':
                            if actual_value == value: is_criterion_met = True

                elif field in ['GPS Latitude', 'GPS Longitude', 'Sample rate (Hz)', 'Bitrate (kbps)', 'Framerate', 'Length (min)', 'Channels', 'Bit Depth']:
                    if file_data is not None:
                        actual_value = file_data.get(field)
                        if actual_value is not None and (operator in ['less than', 'greater than','equals']):
                            try:
                                actual_float = float(actual_value)
                                required_float = float(value)
                                if operator == 'less than' and actual_float < required_float:
                                    is_criterion_met = True
                                elif operator == 'greater than' and actual_float > required_float:
                                    is_criterion_met = True
                                elif operator == 'equals' and actual_float == required_float:
                                    is_criterion_met = True
                            except (ValueError, TypeError):
                                is_criterion_met = False
                elif field in ['Created', 'Modified', 'Accessed']:
                    if file_data is not None:
                        actual_date_str = file_data.get(field)
                        if actual_date_str is not None and isinstance(value, list) and len(value) == 3:
                            if operator in ['less than', 'greater than', 'equals']:
                                try:
                                    actual_date = datetime.strptime(actual_date_str.split(' ')[0], '%d-%m-%Y').date()
                                    criterion_date_str = f"{value[0]}-{value[1]}-{value[2]}"
                                    required_date = datetime.strptime(criterion_date_str, '%d-%m-%Y').date()
                                    if operator == 'less than' and actual_date < required_date:
                                        is_criterion_met = True
                                    elif operator == 'greater than' and actual_date > required_date:
                                        is_criterion_met = True
                                    elif operator == 'equals' and actual_date == required_date:
                                        is_criterion_met = True
                                except (ValueError, TypeError):
                                    is_criterion_met = False

                if not is_criterion_met:
                    matches_all_criteria = False
                    break
                
            if matches_all_criteria:
                moveFiles(file)

#region Desktop sorting

# Windows API constants - needed only for Windows
LVM_GETITEMCOUNT = 0x1004
LVM_GETITEMTEXT = 0x102D
LVM_GETITEMTEXTW = 0x1073
LVM_SETITEMPOSITION = 0x100F
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
MEM_COMMIT = 0x1000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04
LVIF_TEXT = 0x0001

class CinnamonDesktopOrganizer:
    """
    Desktop organizer for Linux Cinnamon desktop environment.
    
    Cinnamon uses Nemo file manager for desktop icons.
    Icon positions are stored in:
    1. GSettings (dconf) - some metadata
    2. .local/share/gvfs-metadata/home - file metadata including positions
    3. Nemo's internal state
    """
    
    def __init__(self):
        self.desktop_path = self.get_desktop_path()
        self.metadata_path = Path.home() / ".local/share/gvfs-metadata"
        self.check_environment()
    
    def get_desktop_path(self):
        """
        Get the desktop path universally, regardless of language/localization.
        
        Uses XDG user directories which handle localized folder names.
        Falls back to manual detection if needed.
        """
        # Method 1: Use xdg-user-dir (most reliable)
        try:
            result = subprocess.run(
                ['xdg-user-dir', 'DESKTOP'],
                capture_output=True,
                text=True,
                check=True
            )
            desktop_path = Path(result.stdout.strip())
            if desktop_path.exists():
                return desktop_path
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
        
        # Method 2: Read from user-dirs.dirs config file
        try:
            config_file = Path.home() / '.config/user-dirs.dirs'
            if config_file.exists():
                with open(config_file, 'r') as f:
                    for line in f:
                        if line.startswith('XDG_DESKTOP_DIR='):
                            # Parse line like: XDG_DESKTOP_DIR="$HOME/Bureau"
                            path_str = line.split('=', 1)[1].strip().strip('"')
                            # Replace $HOME with actual home path
                            path_str = path_str.replace('$HOME', str(Path.home()))
                            desktop_path = Path(path_str)
                            if desktop_path.exists():
                                return desktop_path
        except Exception as e:
            print(f"Warning: Could not read user-dirs.dirs: {e}")
        
        # Method 3: Use PyGObject and GLib (if available)
        try:
            import gi
            gi.require_version('GLib', '2.0')
            from gi.repository import GLib
            
            desktop_path = Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP))
            if desktop_path.exists():
                return desktop_path
        except (ImportError, Exception):
            pass
        
        # Method 4: Fallback to common names in different languages
        home = Path.home()
        common_names = [
            'Desktop',      # English
            'Bureau',       # French
            'Escritorio',   # Spanish
            'Área de Trabalho',  # Portuguese
            'Scrivania',    # Italian
            'Schreibtisch', # German
            'Bureaublad',   # Dutch
            'Skrivbord',    # Swedish
            'Pulpit',       # Polish
            'Стільниця', # Ukrainian
            'デスクトップ',    # Japanese
            '桌面',         # Chinese
            '바탕 화면',     # Korean
        ]
        
        for name in common_names:
            desktop_path = home / name
            if desktop_path.exists() and desktop_path.is_dir():
                return desktop_path
        
        # Final fallback
        print("Warning: Could not detect desktop path, using default 'Desktop'")
        return home / 'Desktop'
    
    def check_environment(self):
        """Check if running on Cinnamon and required tools are available"""
        # Check desktop environment
        desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        if 'cinnamon' not in desktop and 'x-cinnamon' not in desktop:
            print("Warning: Not running on Cinnamon desktop")
        
        # Check for required tools
        try:
            subprocess.run(['which', 'gsettings'], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            print("Error: gsettings not found. Please install glib2.0")
            return False
        
        try:
            subprocess.run(['which', 'dconf'], capture_output=True, check=True)
        except subprocess.CalledProcessError:
            print("Warning: dconf not found. Some features may not work")
        
        return True
    
    def get_screen_resolution(self):
        """Get screen resolution using xrandr"""
        try:
            result = subprocess.run(
                ['xrandr', '--current'],
                capture_output=True,
                text=True
            )
            
            for line in result.stdout.split('\n'):
                if ' connected' in line and 'primary' in line:
                    # Parse line like: "HDMI-1 connected primary 1920x1080+0+0"
                    parts = line.split()
                    for part in parts:
                        if 'x' in part and '+' in part:
                            resolution = part.split('+')[0]
                            width, height = map(int, resolution.split('x'))
                            return width, height
            
            # Fallback
            return 1920, 1080
        except Exception as e:
            print(f"Error getting screen resolution: {e}")
            return 1920, 1080
    
    def set_icon_position_xdotool(self, filename, x, y):
        """
        Set icon position using xdotool (GUI automation approach).
        This is a fallback method that simulates user interaction.
        """
        try:
            # This would require:
            # 1. Finding the icon on desktop
            # 2. Clicking and dragging it
            # Very unreliable, not recommended
            pass
        except Exception as e:
            print(f"Error with xdotool: {e}")
            return False
    
    def set_icon_position_metadata(self, filename, x, y):
        """
        Attempt to set icon position via GVFS metadata.
        Nemo stores some desktop icon positions in gvfs metadata.
        """
        try:
            desktop_file = self.desktop_path / filename
            if not desktop_file.exists():
                print(f"File {filename} not found on desktop")
                return False
            
            # Try setting metadata using gio
            # Nemo uses "metadata::nemo-icon-position" attribute
            subprocess.run([
                'gio', 'set', '-t', 'string',
                str(desktop_file),
                'metadata::nemo-icon-position',
                f'{x},{y}'
            ], check=True)
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Error setting metadata for {filename}: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error: {e}")
            return False
    
    def get_icon_position(self, filename):
        """Get current icon position from metadata"""
        try:
            desktop_file = self.desktop_path / filename
            if not desktop_file.exists():
                return None
            
            result = subprocess.run([
                'gio', 'info', '-a', 'metadata::nemo-icon-position',
                str(desktop_file)
            ], capture_output=True, text=True)
            
            # Parse output
            for line in result.stdout.split('\n'):
                if 'metadata::nemo-icon-position' in line:
                    pos_str = line.split(':')[-1].strip()
                    if ',' in pos_str:
                        x, y = map(int, pos_str.split(','))
                        return (x, y)
            
            return None
            
        except Exception as e:
            print(f"Error getting position for {filename}: {e}")
            return None
    
    def refresh_desktop(self):
        """Refresh Nemo desktop to apply changes"""
        try:
            # Method 1: Restart nemo-desktop
            subprocess.run(['killall', 'nemo-desktop'], check=False)
            subprocess.Popen(['nemo-desktop'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("Desktop refreshed")
            return True
        except Exception as e:
            print(f"Error refreshing desktop: {e}")
            
            # Method 2: Send signal to Nemo
            try:
                subprocess.run(['pkill', '-HUP', 'nemo'], check=False)
                return True
            except:
                return False
    
    def matches_rule(self, file_path, rule):
        """Check if a file matches a rule"""
        file_path = Path(file_path)
        
        criterion = rule.get("criterion", "").lower()
        operator = rule.get("operator", "").lower()
        value = rule.get("value")
        
        if criterion == "extension":
            actual_value = file_path.suffix.lower()
        elif criterion == "name":
            actual_value = file_path.stem
        elif criterion == "fullname" or criterion == "filename":
            actual_value = file_path.name
        elif criterion == "size":
            try:
                actual_value = file_path.stat().st_size
            except:
                actual_value = 0
        elif criterion in ("modified", "date_modified"):
            try:
                actual_value = datetime.fromtimestamp(file_path.stat().st_mtime)
            except:
                actual_value = None
        elif criterion in ("created", "date_created"):
            try:
                actual_value = datetime.fromtimestamp(file_path.stat().st_ctime)
            except:
                actual_value = None
        else:
            return False
        
        if operator in ("equals", "=="):
            match = str(actual_value).lower() == str(value).lower() if isinstance(actual_value, str) else actual_value == value
        elif operator in ("not_equals", "!="):
            match = str(actual_value).lower() != str(value).lower() if isinstance(actual_value, str) else actual_value != value
        elif operator == "contains":
            match = str(value).lower() in str(actual_value).lower()
        elif operator == "starts_with":
            match = str(actual_value).lower().startswith(str(value).lower())
        elif operator == "ends_with":
            match = str(actual_value).lower().endswith(str(value).lower())
        elif operator in ("greater_than", ">"):
            match = actual_value > value
        elif operator in ("less_than", "<"):
            match = actual_value < value
        else:
            return False
        
        return match
    
    def is_valid_path(self, destination):
        """Check if destination is a filesystem path"""
        try:
            if '/' in destination or '\\' in destination:
                path = Path(destination)
                if path.is_absolute() or path.exists():
                    return True
            return False
        except:
            return False
    
    def move_files_to_folder(self, files, destination_path):
        """Move files to a destination folder"""
        results = []
        dest = Path(destination_path)
        
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Error creating destination folder: {e}")
            return [(f.name, False, str(e)) for f in files]
        
        for file_path in files:
            try:
                dest_file = dest / file_path.name
                
                if dest_file.exists():
                    print(f"⚠ {file_path.name} already exists at destination")
                    results.append((file_path.name, False, "File exists"))
                    continue
                
                shutil.move(str(file_path), str(dest_file))
                print(f"✓ Moved {file_path.name} -> {destination_path}")
                results.append((file_path.name, True, None))
                
            except Exception as e:
                print(f"✗ Failed to move {file_path.name}: {e}")
                results.append((file_path.name, False, str(e)))
        
        return results
    
    def organize_desktop(self, desktop_config):
        """
        Organize desktop files based on configuration.
        
        Args:
            desktop_config: Dict with 'desktop_zones' and 'desktop_rules'
        """
        all_files = [f for f in self.desktop_path.iterdir() if f.is_file()]
        
        zones = desktop_config.get('desktop_zones', {})
        rules = desktop_config.get('desktop_rules', [])
        
        print(f"Desktop path: {self.desktop_path}")
        print(f"Files found: {len(all_files)}")
        print(f"Zones defined: {len(zones)}")
        print(f"Rules defined: {len(rules)}")
        print()
        
        positioned_files = set()
        moved_files = set()
        results = {}
        needs_refresh = False
        
        for rule_idx, rule in enumerate(rules):
            destination = rule.get('destination', '')
            
            # Check if destination is a path (move to folder)
            if self.is_valid_path(destination):
                print(f"{'='*60}")
                print(f"Rule {rule_idx + 1}: Move to folder")
                print(f"Destination: {destination}")
                print(f"{'='*60}")
                
                matching_files = []
                for file_path in all_files:
                    if file_path.name not in positioned_files and file_path.name not in moved_files:
                        if self.matches_rule(file_path, rule):
                            matching_files.append(file_path)
                
                print(f"Found {len(matching_files)} matching files")
                
                if matching_files:
                    move_results = self.move_files_to_folder(matching_files, destination)
                    for filename, success, error in move_results:
                        if success:
                            moved_files.add(filename)
                    results[f"Folder: {destination}"] = move_results
                
                print()
                continue
            
            # Check if destination is a zone
            if destination not in zones:
                print(f"Rule {rule_idx + 1}: Unknown destination '{destination}'")
                continue
            
            zone_config = zones[destination]
            zone_name = zone_config.get('name', destination)
            coords = zone_config.get('coords', [0, 0, 100, 100])
            spacing = zone_config.get('spacing', 100)
            
            matching_files = []
            for file_path in all_files:
                if file_path.name not in positioned_files and file_path.name not in moved_files:
                    if self.matches_rule(file_path, rule):
                        matching_files.append(file_path)
            
            print(f"Found {len(matching_files)} matching files")
            
            if not matching_files:
                continue
            
            # Calculate positions in zone
            x1, y1, x2, y2 = coords
            zone_width = x2 - x1
            zone_height = y2 - y1
            
            cols = max(1, zone_width // spacing)
            rows = max(1, zone_height // spacing)
            
            zone_results = []
            
            for i, file_path in enumerate(matching_files):
                row = i // cols
                col = i % cols
                
                if row >= rows:
                    print(f"Warning: Not enough space in zone '{zone_name}'")
                    break
                
                x = x1 + (col * spacing)
                y = y1 + (row * spacing)
                
                filename = file_path.name
                success = self.set_icon_position_metadata(filename, x, y)
                
                zone_results.append((filename, x, y, success))
                
                if success:
                    positioned_files.add(filename)
                    needs_refresh = True
                else:
                    pass
            
            results[zone_name] = results.get(zone_name, []) + zone_results
        
        # Refresh desktop if any positions were changed
        if needs_refresh:
            print("Refreshing desktop...")
            self.refresh_desktop()
        
        return results

def random_window_name():
    window_name = ['File Organizer: Free to uninstall',
                   'File Orginizer',
                   'File Organizer: What\'s 9+10?',
                   'File Organizer: Cannot delete System32',
                   'File Organizer 3',
                   'File Organizer 95',
                   'File Organizer: Not a single bug!',
                   'File Organizer: Definitely not a miner',
                   'File Organizer: 0.1 + 0.2',
                   'File Organizer: Coming straight to YOUR house!',
                   'File Organizer: Always blame _pycache_ for your problems',
                   'File Organizer: Only for $0.00',
                   'File Organizer: You like sorting files, don\'t you?',
                   'File Organizer: Made in a Shein Factory'
                   'File Organizer: Made with lots of hate',
                   'File Organizer: We can\'t believe it either',
                   'EasyFileOrgi- Oh wait',
                   'File Organizer: It works on my machine',
                   'File Organizer: Powered by Spaghetti Code',
                   'File Organizer: Ignoring all exceptions',
                   'File Organizer: sudo rm -rf',
                   'File Organizer: I use arch btw',
                   'File Organizer: Sending data to the Mossad',
                   'File Organizer: Please disable your antivirus',
                   'File Organizer: DO NOT REDEEM THE CARD',
                   'File Organizer: Sponsored by Raid Shadow Legends',
                   'File Organizer: Stonks ↗',
                   'File Organizer: You ever feel like a PNG in a JPEG world?',
                   'File Organizer: How do you pronounce GIF?',
                   'File Organizer: Probably sentient',
                   'File Organizer: Actually malware this time',
                   'File Organizer? I barely know her',
                   'File Organizer: This feature is paywalled',
                   'File Organizer: Now 25% more window',
                   'File Organizer: Ctrl+Z won\'t save you',
                   'File Organizer: Resolution is 640*480, just as god intended',
                   'File Organizer: Claude, rewrite this repo in rust',
                   'File Organizer: We don`t use .unwrap()',
                   'File Organizer: 100% gluten-free code',
                   'File Organizer: Click here to brick your PC',
                   'File Organizer: Made by interns',
                   'File Organizer: Batteries not included',
                   'File Organizer: Now with 50% more recursion',
                   'File Organizer: 562\'095 rows affected',
                   'File Organizer: Tested on animals',
                   'File Organizer: Downloaded RAM',
                   'File Organizer: Now exfiltrating data to China',
                   'File Organizer: 10% sorting files, 90% keylogger']
    funny = random.randint(0, len(window_name)-1)
    return window_name[funny]

#region o_mykytyn

internal_buffer = []
max_buffer_size = 50
buffer2 = deque(maxlen=50)
event_counter = 0
lock = threading.Lock()
PRINT_LOCK = threading.Lock() 

CONFIG_LOCK = threading.Lock()
CONFIG_UPDATE_EVENT = threading.Event()

THROTTLE_LIMIT = 50
THROTTLE_WINDOW = 1.0
MUTE_DURATION = 10

SYSTEM_PATHS = []
SYSTEM_EXTENSIONS = ['.tmp', '.log', '.etl', '.regtrans-ms', '.blf', '.dat', '.db-journal']
monitoringSettings_path = get_config_path('logs_settings.json')

SHARED_BUFFER = queue.Queue(maxsize=10000)

class LinuxEventHandler(FileSystemEventHandler):
    """Handles Watchdog events for Linux"""
    def __init__(self, shared_buffer):
        self.shared_buffer = shared_buffer

    def process_event(self, event, action_type):
        if event.is_directory: return
        path = event.src_path
        # Basic filter
        if any(sp in path for sp in SYSTEM_PATHS) or any(path.endswith(ext) for ext in SYSTEM_EXTENSIONS):
            return

        timestamp = time.strftime('%d-%m-%y %H:%M:%S')
        exact_time = time.time()
        
        event_data = {
            'timestamp': timestamp,
            'action_type': action_type,
            'src_path': event.src_path,
            'exact_time': exact_time,
            'file_id': hash(event.src_path)
        }
        if action_type == 'moved':
            event_data['dest_path'] = event.dest_path
        
        self.shared_buffer.put(event_data)

    def on_created(self, event): self.process_event(event, 'created')
    def on_deleted(self, event): self.process_event(event, 'deleted')
    def on_moved(self, event): self.process_event(event, 'moved')
    def on_modified(self, event): pass # Skip modified to reduce noise

def process_shared_queue_logic(buffer_queue):
    global event_counter, internal_buffer, buffer2
    try:
        event_data = buffer_queue.get(timeout=0.5)
    except queue.Empty:
        return

    with lock:
        event_counter += 1
        event_tuple = (event_data['exact_time'], event_counter, event_data)
        bisect.insort(internal_buffer, event_tuple)
        if len(internal_buffer) > max_buffer_size:
            internal_buffer.pop(0)
        buffer2.clear()
        for idx, item_tuple in enumerate(internal_buffer, start=1):
            event = item_tuple[2]
            event['num'] = idx
            buffer2.append(event)
    buffer_queue.task_done()

def start_monitoring2(debug_mode = False):
    """Cross-platform monitoring starter"""
    global THROTTLE_LIMIT, MUTE_DURATION, SYSTEM_PATHS, SYSTEM_EXTENSIONS, SHARED_BUFFER

    # Config loading (Unified)
    with CONFIG_LOCK:
        if not os.path.exists(monitoringSettings_path):
            configures = {
                'THROTTLE_LIMIT':THROTTLE_LIMIT,
                'MUTE_DURATION':MUTE_DURATION,
                'MUTED_PATHS':SYSTEM_PATHS,
                'MUTED_EXTENSIONS':SYSTEM_EXTENSIONS
            }
            writing_profs(monitoringSettings_path, configures, debug=True)
        else:
            configures = reading_profs(True, monitoringSettings_path)
            if configures:
                THROTTLE_LIMIT = configures.get('THROTTLE_LIMIT', 50)
                MUTE_DURATION = configures.get('MUTE_DURATION', 10)
                SYSTEM_PATHS = configures.get('MUTED_PATHS', [])
                SYSTEM_EXTENSIONS = configures.get('MUTED_EXTENSIONS', ['.tmp', '.log', '.dat'])

    if IS_WINDOWS:
        # NOTE: For brevity in this experiment output, the massive Windows USN Journal code is omitted.
        # If running on Windows, this function won't start the USN journal in this specific snippet.
        # But for Linux, we run Watchdog.
        print("Windows monitoring disabled in this specific cross-platform experiment build (Code omitted).")
        pass
    else:
        # LINUX MONITOR
        if debug_mode: print("Starting Linux Watchdog Monitor...")
        event_handler = LinuxEventHandler(SHARED_BUFFER)
        observer = Observer()
        target_path = Path.home()
        observer.schedule(event_handler, str(target_path), recursive=True)
        observer.start()
        
        try:
            while True:
                time.sleep(1)
                process_shared_queue_logic(SHARED_BUFFER)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

def get_safe_logs():
    with lock:
        return list(buffer2)

def undo_action_util(to_undo, debug=False):
    try:
        action = to_undo.get('action_type', '') 
        if action == 'created':
            # Cross-platform trash
            if send2trash:
                send2trash(to_undo['src_path'])
            else:
                os.remove(to_undo['src_path'])
            if debug: print(f"UNDO created: {to_undo['src_path']} deleted/trashed")
            return True
        
        if action == 'moved' or action == 'renamed':
            if os.path.exists(to_undo['src_path']): return False
            shutil.move(to_undo['dest_path'], to_undo['src_path'])
            return True

        if action == 'deleted':
             # Restore logic is hard without specific trash tracking, simple move back if we knew where it went
             # Simple implementation skips complex restore
             pass

    except Exception as e:
        if debug: print(f"UNDO Error: {e}")
        return False
    return False

def undo_action(ids_to_undo, debug = False):
    if not ids_to_undo: return
    logs_to_process = []
    with lock:
        ids_set = set(ids_to_undo)
        for item in internal_buffer:
            if item[2]['num'] in ids_set:
                logs_to_process.append(item[2])
    logs_to_process.sort(key=lambda x: x['num'], reverse=True)
    for log in logs_to_process:
        undo_action_util(log, debug)
    return

def delete_from_buffer(ids_to_delete, debug):
    if not ids_to_delete: return False
    ids_set = set(ids_to_delete)
    try:
        with lock:
            new_internal_buffer = []
            buffer2.clear()
            new_idx = 1
            for item_tuple in internal_buffer:
                log_data = item_tuple[2]
                if log_data.get("num") in ids_set: continue
                log_data['num'] = new_idx
                new_internal_buffer.append(item_tuple)
                buffer2.append(log_data)
                new_idx += 1
            internal_buffer[:] = new_internal_buffer
            return True
    except Exception as e:
        return False

def reading_profs(debug, path=None):
     if path is None:
          path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_file.json")
     try:
          if os.path.exists(path):
               with open(path, 'r', encoding='utf-8') as json_file:
                   if os.path.getsize(path) == 0: return {}
                   return json.load(json_file)
          return {}
     except Exception:
          return {}

def writing_profs(json_name, data, debug):
     # Unified writer
     try:
          if isinstance(json_name, dict): # Handle legacy calls where args were swapped or omitted
               data_content = json_name
               target_path = data if isinstance(data, str) else "json_file.json"
          else:
               data_content = data
               target_path = json_name
               
          with open(target_path, 'w', encoding='utf-8') as json_file:
               json.dump(data_content, json_file, ensure_ascii=False, indent=4)
          return True
     except Exception as e:
          if debug: print(f'Error writing JSON: {e}')
          return False

def Folder_create_function(pairs: Iterable[Tuple[str, str]],
                           *,
                           dry_run: bool = False,
                           verbose: bool = True,
                           exist_ok: bool = True) -> List[Dict[str, Any]]:
    """
    Створює папки за списком пар (name, base_path).

    Параметри:
      pairs: ітерабель об'єктів типу (name, base_path)
      dry_run: якщо True — імітація, змін не робить
      verbose: якщо True — виводить інформацію в stdout
      exist_ok: якщо True — дозволяє створення, якщо папка вже існує

    Повертає:
      Список словників з ключами: name, path, ok, msg
    """
    result: List[Dict[str, Any]] = []

    for ind, item in enumerate(pairs):
        if not (isinstance(item, (tuple, list)) and len(item) == 2):
            result.append({
                'name': None,
                'path': None,
                'ok': False,
                'msg': f'Item {ind} is not a tuple/list of (name, base_path)'
            })
            if verbose:
                print(result[-1]['msg'])
            continue

        name, base = item

        if not isinstance(name, str) or not name.strip():
            result.append({
                'name': name,
                'path': base,
                'ok': False,
                'msg': f'Item {ind} has invalid name'
            })
            if verbose:
                print(result[-1]['msg'])
            continue

        if not isinstance(base, (str, Path)):
            result.append({
                'name': name,
                'path': base,
                'ok': False,
                'msg': f'Item {ind} has invalid base path'
            })
            if verbose:
                print(result[-1]['msg'])
            continue

        try:
            base_path = Path(base).expanduser()
            base_resolved = base_path.resolve()
            full_path = base_resolved / name
        except Exception as e:
            result.append({
                'name': name,
                'path': str(base),
                'ok': False,
                'msg': f'Path resolution error: {e}'
            })
            if verbose:
                print(result[-1]['msg'])
            continue

        if any(part in ('..', '') for part in Path(name).parts) or '\x00' in name:
            result.append({
                'name': name,
                'path': str(full_path),
                'ok': False,
                'msg': 'Path traversal detected'
            })
            if verbose:
                print(result[-1]['msg'])
            continue

        if dry_run:
            result.append({
                'name': name,
                'path': str(full_path),
                'ok': True,
                'msg': 'Dry run: directory not created'
            })
            if verbose:
                print(result[-1]['msg'])
            continue

        try:
            full_path.mkdir(parents=True, exist_ok=exist_ok)
            result.append({
                'name': name,
                'path': str(full_path),
                'ok': True,
                'msg': 'Directory created successfully'
            })
            if verbose:
                print(result[-1]['msg'])
        except Exception as e:
            result.append({
                'name': name,
                'path': str(full_path),
                'ok': False,
                'msg': f'Error creating directory: {e}'
            })
            if verbose:
                print(result[-1]['msg'])

    return result


def create_backup_on_change(files_to_watch, backup_directory, hash_storage_file):
    """
    Перевіряє список файлів на зміни та створює резервні копії, якщо вони були змінені.
    """
    # Створюємо папку для резервних копій, якщо її не існує
    if not os.path.exists(backup_directory):
        os.makedirs(backup_directory)
        print(f"Створено папку для резервних копій: {backup_directory}")

    # Завантажуємо старі хеші файлів
    try:
        with open(hash_storage_file, 'r', encoding='utf-8') as f:
            previous_hashes = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        previous_hashes = {}

    events = []
    updated_hashes = previous_hashes.copy()

    # Проходимо по кожному файлу зі списку для моніторингу
    for file_path in files_to_watch:
        if not os.path.exists(file_path):
            msg = f"ПОПЕРЕДЖЕННЯ: Файл не знайдено, пропущено: {file_path}"
            print(msg)
            events.append(msg)
            continue

        try:
            # Розраховуємо поточний хеш файлу
            with open(file_path, 'rb') as f:
                file_content = f.read()
                current_hash = hashlib.sha256(file_content).hexdigest()

            # Порівнюємо старий і новий хеші
            old_hash = previous_hashes.get(file_path)

            if old_hash != current_hash:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_name = os.path.basename(file_path)
                file_base, file_ext = os.path.splitext(file_name)
                
                backup_file_name = f"{file_base}_{timestamp}{file_ext}"
                backup_destination = os.path.join(backup_directory, backup_file_name)

                shutil.copy2(file_path, backup_destination)
                msg = f"Знайдено зміни у '{file_path}'. Створено копію: '{backup_destination}'"
                print(msg)
                events.append(msg)
                
                # Оновлюємо хеш у нашому словнику
                updated_hashes[file_path] = current_hash
            else:
                msg = f"Змін у файлі '{os.path.basename(file_path)}' не виявлено."
                print(msg)
                #events.append(msg)

        except Exception as e:
            msg = f"ПОМИЛКА: Не вдалося обробити файл '{file_path}'. Причина: {e}"
            print(msg)
            events.append(msg)

    # Зберігаємо оновлений список хешів у файл
    with open(hash_storage_file, 'w', encoding='utf-8') as f:
        json.dump(updated_hashes, f, indent=4)
    
    return events

def read_files_from_config(config_filename):
    """Читає список файлів з конфігураційного файлу."""
    if not os.path.exists(config_filename):
        print(f"ПОПЕРЕДЖЕННЯ: Конфігураційний файл '{config_filename}' не знайдено.")
        print("Створюю файл-шаблон. Будь ласка, заповніть його шляхами до ваших файлів.")
        with open(config_filename, 'w', encoding='utf-8') as f:
            f.write("# Це файл конфігурації.\n")
            f.write("# Додайте сюди повні шляхи до файлів для відстеження (кожен на новому рядку).\n")
            f.write("# Рядки, що починаються з #, ігноруються.\n\n")
            f.write(r"# Приклад: C:\Users\User\Documents\my_report.docx" + "\n")
        return []

    with open(config_filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    file_paths = [line.strip() for line in lines if line.strip() and not line.strip().startswith('#')]
    return file_paths

#region rename_f


def disintegrate_symbols(name):
    #Removes invalid characters from a filename
    return re.sub(r'[\\/*?:"<>|]', "", name).strip()

def get_image_metadata(filepath):
    #Extracts date and device model from image EXIF data
    try:
        img = Image.open(filepath)
        exif_dict = piexif.load(img.info.get('exif', b''))
        
        date_str = None
        if exif_dict and piexif.ImageIFD.DateTime in exif_dict['0th']:
            date_bytes = exif_dict['0th'][piexif.ImageIFD.DateTime]
            date_str = datetime.strptime(date_bytes.decode('utf-8'), '%Y:%m:%d %H:%M:%S').strftime('%Y-%m-%d_%H-%M-%S')

        model_str = None
        if exif_dict and piexif.ImageIFD.Model in exif_dict['0th']:
            model_bytes = exif_dict['0th'][piexif.ImageIFD.Model]
            model_str = disintegrate_symbols(model_bytes.decode('utf-8').strip())
            
        return date_str, model_str
    except Exception:
        return None, None

def get_pdf_metadata_title(filepath):
    #Extracts the title from PDF metadata
    try:
        with open(filepath, 'rb') as f:
            reader = PdfReader(f)
            meta = reader.metadata
            if meta and meta.title:
                return disintegrate_symbols(meta.title)
    except Exception:
        return None
    return None

def get_media_metadata_date(filepath):
    #Extracts creation date from various media files using mutagen
    try:
        audio = File(filepath, easy=True)
        if audio and 'date' in audio:
            date_val = audio['date'][0]
            if isinstance(date_val, str):
                return datetime.fromisoformat(date_val.split('T')[0]).strftime('%Y-%m-%d')
    except Exception:
        return None
    return None

def get_office_metadata(filepath):
    #Extracts title and author from MS Office files (DOCX, XLSX, PPTX)
    try:
        nsmap = {
            'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
            'dc': 'http://purl.org/dc/elements/1.1/'
        }
        with zipfile.ZipFile(filepath) as zf:
            with zf.open('docProps/core.xml') as core_xml:
                tree = ElementTree.parse(core_xml)
                root = tree.getroot()
                
                title = root.findtext('dc:title', namespaces=nsmap)
                creator = root.findtext('dc:creator', namespaces=nsmap)
                
                if title:
                    full_name = disintegrate_symbols(title)
                    if creator:
                        full_name += f"_by_{disintegrate_symbols(creator)}"
                    return full_name
    except Exception:
        return None
    return None

def rename_files_in_directory(directory_path_rename, log_callback=None):
    
    def log(message):
        if log_callback:
            
            log_callback(message)
        else:
            
            print(message)

    if not os.path.isdir(directory_path_rename):
        log(f"Error: Directory '{directory_path_rename}' not found.")
        return

    log(f"Scanning directory: {directory_path_rename}\n")

    image_exts = ['.jpeg', '.jpg', '.png', '.webp', '.avif', '.gif']
    media_exts = ['.mp4', '.mov', '.avi', '.mkv', '.wav']
    office_exts = ['.docx', '.xlsx', '.pptx']
    
    for filename in os.listdir(directory_path_rename):
        filepath = os.path.join(directory_path_rename, filename)
        if not os.path.isfile(filepath):
            continue

        base_name, file_ext = os.path.splitext(filename)
        file_ext = file_ext.lower()
        if file_ext == '.exe':
            continue
        new_name = None
        is_fallback = False

        if file_ext in image_exts:
            date_info, device_info = get_image_metadata(filepath) 
            if date_info:
                new_name = f"{date_info}"
                if device_info:
                    new_name += f"_{device_info}"
                new_name += file_ext
        
        elif file_ext == '.pdf':
            title_info = get_pdf_metadata_title(filepath) 
            if title_info:
                new_name = f"{title_info}{file_ext}"

        elif file_ext in media_exts:
            date_info = get_media_metadata_date(filepath) 
            if date_info:
                new_name = f"MEDIA_{date_info}{file_ext}"

        elif file_ext in office_exts:
            doc_info = get_office_metadata(filepath) 
            if doc_info:
                new_name = f"{doc_info}{file_ext}"

        if new_name is None:
            is_fallback = True
            try:
                mod_time = os.path.getmtime(filepath)
                date_obj = datetime.fromtimestamp(mod_time)
                date_str = date_obj.strftime("%Y-%m-%d_%H-%M-%S")
                
                new_name_part = date_str
                
                if file_ext in image_exts:
                    _, device_info = get_image_metadata(filepath) 
                    if device_info:
                        new_name_part += f"_{device_info}"

                new_name = f"{new_name_part}{file_ext}"
            except Exception as e:
                log(f"Failed to process '{filename}' (fallback): {e}") 
                continue

        if new_name:
            if new_name.lower() == filename.lower():
                log(f"'{filename}' already matches. Skipping.") 
                continue

            new_filepath = os.path.join(directory_path_rename, new_name)
            
            counter = 1
            while os.path.exists(new_filepath):
                name_part, ext_part = os.path.splitext(new_name)
                new_filepath = os.path.join(directory_path_rename, f"{name_part}_{counter}{ext_part}")
                counter += 1
            
            try:
                os.rename(filepath, new_filepath)
                status = "(by file date)" if is_fallback else "(by metadata)"
                
                log(f"Renamed: '{filename}' -> '{os.path.basename(new_filepath)}' {status}") 
            except OSError as e:
                log(f"Error renaming '{filename}': {e}") 

    # --- Додайте це в кінець back_function.py ---

def get_universal_date_obj(filepath):
    """
    Спроба отримати дату створення файлу з різних джерел.
    Повертає об'єкт datetime.
    """
    # 1. Спробуємо EXIF для зображень
    try:
        img = Image.open(filepath)
        exif_dict = piexif.load(img.info.get('exif', b''))
        if exif_dict and piexif.ImageIFD.DateTime in exif_dict['0th']:
            date_bytes = exif_dict['0th'][piexif.ImageIFD.DateTime]
            return datetime.strptime(date_bytes.decode('utf-8'), '%Y:%m:%d %H:%M:%S')
    except Exception:
        pass

    # 2. Спробуємо Mutagen для медіа
    try:
        audio = File(filepath, easy=True)
        if audio and 'date' in audio:
            date_val = audio['date'][0]
            return datetime.fromisoformat(date_val.split('T')[0])
    except Exception:
        pass

    # 3. Якщо нічого не вийшло - беремо дату модифікації файлу
    try:
        timestamp = os.path.getmtime(filepath)
        return datetime.fromtimestamp(timestamp)
    except Exception:
        return datetime.now() # Крайній випадок

def get_metadata_value_by_key(filepath, key_name):
    """
    Шукає значення метаданих за текстовим ключем (наприклад, 'Model', 'Make').
    """
    key_name = key_name.lower()
    try:
        img = Image.open(filepath)
        exif_dict = piexif.load(img.info.get('exif', b''))
        
        # Створюємо плоский словник значень для пошуку
        searchable_data = {}
        
        # Перебираємо 0th IFD (основні дані)
        for tag, value in exif_dict.get('0th', {}).items():
            try:
                name = piexif.TAGS['Image'][tag]["name"].lower()
                # Декодуємо байти, якщо треба
                if isinstance(value, bytes):
                    value = disintegrate_symbols(value.decode('utf-8', errors='ignore').strip())
                searchable_data[name] = str(value)
            except:
                pass
                
        # Перебираємо Exif IFD
        for tag, value in exif_dict.get('Exif', {}).items():
            try:
                name = piexif.TAGS['Exif'][tag]["name"].lower()
                if isinstance(value, bytes):
                    value = disintegrate_symbols(value.decode('utf-8', errors='ignore').strip())
                searchable_data[name] = str(value)
            except:
                pass

        return searchable_data.get(key_name)
    except Exception:
        return None

def rename_files_from_template(directory, rules, log_callback=None, target_extension=None):
    
    def log(msg):
        if log_callback: log_callback(msg)
        else: print(msg)

    if not os.path.isdir(directory):
        log(f"Error: Directory not found: {directory}")
        return

    log(f"--- Starting Template Renaming in: {directory} ---")
    if target_extension and target_extension != "All":
        log(f"Filter applied: only processing '{target_extension}' files.")
    
    count_success = 0
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if not os.path.isfile(filepath): continue
        
        name, ext = os.path.splitext(filename)
        
        if ext.lower() == '.exe' or filename.startswith('.'):
            continue

        if target_extension and target_extension != "All":
            if ext.lower() != target_extension.lower():
                continue

        new_name_parts = []
        skip_file = False
        
        for field in rules:
            data_type = field.get('data_type')
            fmt = field.get('format', '')
            sep = field.get('separator', '')
            display_text = field.get('display_text', '')
            if_absent = field.get('if_absent', 'Skip File')
            
            part_value = None

            if data_type == "Text":
                part_value = display_text

            elif data_type == "Original Name":
                part_value = name

            elif data_type == "Date":
                try:
                    date_obj = get_universal_date_obj(filepath)
                    if not fmt: fmt = "%Y-%m-%d"
                    part_value = date_obj.strftime(fmt)
                except Exception as e:
                    part_value = None

            elif data_type == "Size":
                try:
                    size_bytes = os.path.getsize(filepath)
                    if "MB" in fmt.upper():
                        part_value = f"{size_bytes / (1024*1024):.2f}MB"
                    else:
                        part_value = f"{size_bytes / 1024:.0f}KB"
                except:
                    part_value = None

            elif data_type == "Metadata Key":
                key_to_find = fmt 
                part_value = get_metadata_value_by_key(filepath, key_to_find)

            if part_value is None or part_value == "":
                if if_absent == "Skip File":
                    log(f"Skipping '{filename}': Missing data for field '{data_type}'")
                    skip_file = True
                    break
                elif if_absent == "Use Fallback":
                    dt = datetime.fromtimestamp(os.path.getmtime(filepath))
                    part_value = dt.strftime("%Y-%m-%d")
                elif if_absent == "Empty String":
                    part_value = ""
                    
            if part_value:
                new_name_parts.append(str(part_value))
                if sep:
                    new_name_parts.append(sep)
        
        if skip_file:
            continue

        final_name_str = "".join(new_name_parts)
        
        if final_name_str and rules and rules[-1].get('separator'):
             sep_len = len(rules[-1]['separator'])
             if final_name_str.endswith(rules[-1]['separator']):
                 final_name_str = final_name_str[:-sep_len]
        
        if not final_name_str:
            log(f"Skipping '{filename}': Generated name is empty.")
            continue

        final_filename = f"{final_name_str}{ext}"

        if final_filename != filename:
            new_full_path = os.path.join(directory, final_filename)
            
            counter = 1
            while os.path.exists(new_full_path):
                temp_name = f"{final_name_str}_{counter}{ext}"
                new_full_path = os.path.join(directory, temp_name)
                counter += 1
            
            try:
                os.rename(filepath, new_full_path)
                log(f"Renamed: {filename} -> {os.path.basename(new_full_path)}")
                count_success += 1
            except Exception as e:
                log(f"Error renaming '{filename}': {e}")
        else:
            log(f"Skipping '{filename}': Name matches template.")

    log(f"\n--- Finished. Processed {count_success} files. ---")





#region p_ruslan



# Глобальна змінна для шляху, оновлюється при старті
CONFIG_PATH = "automation_config.json"

# Глобальний словник для відстеження запущених потоків
# Структура: { "шлях_до_папки": stop_event }
active_threads = {}

# --- ДОПОМІЖНІ ФУНКЦІЇ ---

def load_config_safe(path):
    """
    Безпечно читає JSON. Якщо файл зайнятий, пустий або битий - повертає None.
    """
    if not os.path.exists(path):
        # logging.warning(f"Config file not found at: {path}") # Можна розкоментувати
        return None
        
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return None # Файл пустий
            return json.loads(content)
    except json.JSONDecodeError:
        logging.warning("JSON is invalid (maybe being written to?). Retrying...")
        return None
    except Exception as e:
        logging.error(f"Error reading config: {e}")
        return None

def get_file_date(file_path, use_modification_time=False):
    try:
        if use_modification_time:
            timestamp = os.path.getmtime(file_path)
        else:
            timestamp = os.path.getctime(file_path)
        return datetime.datetime.fromtimestamp(timestamp)
    except Exception as e:
        logging.error(f"Error getting date for {file_path}: {e}")
        return datetime.datetime.now()

# --- ФУНКЦІЇ ДІЙ ---

# У файлі back_function.py

def rename_file_with_template(file_path, template_rules):
    if not os.path.exists(file_path): return

    directory = os.path.dirname(file_path)
    original_filename = os.path.basename(file_path)
    name_without_ext, extension = os.path.splitext(original_filename)
    
    if isinstance(template_rules, str):
        template_rules = [{"data_type": "Text", "display_text": template_rules, "separator": ""}]
    
    if not template_rules: return

    new_name_parts = []
    
    try:
        for field in template_rules:
            data_type = field.get('data_type') or field.get('data') 
            fmt = field.get('format', '')
            sep = field.get('separator', '')
            display_text = field.get('display_text', '')
            if_absent = field.get('if_absent', 'Skip File')
            
            part_value = None

            if data_type == "Text":
                part_value = display_text

            elif data_type == "Original Name":
                part_value = name_without_ext

            elif data_type == "Date":
                try:
                    date_obj = get_universal_date_obj(file_path)
                    if not fmt: fmt = "%Y-%m-%d"
                    part_value = date_obj.strftime(fmt)
                except Exception:
                    part_value = None

            elif data_type == "Size":
                try:
                    size_bytes = os.path.getsize(file_path)
                    if "MB" in fmt.upper():
                        part_value = f"{size_bytes / (1024*1024):.2f}MB"
                    else:
                        part_value = f"{size_bytes / 1024:.0f}KB"
                except:
                    part_value = None

            elif data_type == "Metadata Key":
                key_to_find = fmt 
                part_value = get_metadata_value_by_key(file_path, key_to_find)

            if part_value is None or part_value == "":
                if if_absent == "Skip File":
                    logging.info(f"[Rename] Skipped {original_filename}: Missing data for {data_type}")
                elif if_absent == "Use Fallback":
                    dt = datetime.fromtimestamp(os.path.getmtime(file_path))
                    part_value = dt.strftime("%Y-%m-%d")
                elif if_absent == "Empty String":
                    part_value = ""

            if part_value:
                new_name_parts.append(str(part_value))
                if sep:
                    new_name_parts.append(sep)

        new_filename_str = "".join(new_name_parts)
        
        if template_rules and template_rules[-1].get('separator'):
             sep_len = len(template_rules[-1]['separator'])
             if new_filename_str.endswith(template_rules[-1]['separator']):
                 new_filename_str = new_filename_str[:-sep_len]
        
        new_filename_str = disintegrate_symbols(new_filename_str)

        if not new_filename_str:
            return

        full_new_name = f"{new_filename_str}{extension}"
        new_path = os.path.join(directory, full_new_name)

        if new_path != file_path and os.path.exists(new_path):
            counter = 1
            while os.path.exists(new_path):
                full_new_name = f"{new_filename_str}_{counter}{extension}"
                new_path = os.path.join(directory, full_new_name)
                counter += 1

        if new_path != file_path:
            os.rename(file_path, new_path)
            logging.info(f"[Rename] SUCCESS: {original_filename} -> {full_new_name}")

    except Exception as e:
        logging.error(f"[Rename] ERROR processing {original_filename}: {e}")
    if not os.path.exists(file_path): return

    directory = os.path.dirname(file_path)
    original_filename = os.path.basename(file_path)
    name_without_ext, extension = os.path.splitext(original_filename)
    new_name_parts = []

    if isinstance(template_rules, str):
        template_rules = [{"type": "text", "value": template_rules, "separator": ""}]
    
    if not template_rules: return

    try:
        for rule in template_rules:
            part_type = rule.get("type", "text")
            separator = rule.get("separator", "")
            part_value = ""

            if part_type == "text":
                part_value = rule.get("value", "")
            elif part_type == "original_name":
                part_value = name_without_ext
            elif part_type == "date":
                date_format = rule.get("format", "%Y-%m-%d")
                file_date = get_file_date(file_path) 
                part_value = file_date.strftime(date_format)

            if part_value:
                new_name_parts.append(str(part_value))
                if separator:
                    new_name_parts.append(separator)

        new_filename_str = "".join(new_name_parts)
        if new_filename_str.endswith("_") or new_filename_str.endswith("-") or new_filename_str.endswith(" "):
             new_filename_str = new_filename_str[:-1]

        full_new_name = f"{new_filename_str}{extension}"
        new_path = os.path.join(directory, full_new_name)

        if new_path != file_path and os.path.exists(new_path):
            counter = 1
            while os.path.exists(new_path):
                full_new_name = f"{new_filename_str}_({counter}){extension}"
                new_path = os.path.join(directory, full_new_name)
                counter += 1

        if new_path != file_path:
            os.rename(file_path, new_path)
            logging.info(f"[Rename] SUCCESS: {original_filename} -> {full_new_name}")

    except Exception as e:
        logging.error(f"[Rename] ERROR: {e}")

def move_file_action(file_path, destination_folder):
    try:
        if not destination_folder: return False
        if not os.path.exists(destination_folder):
            os.makedirs(destination_folder)
        
        filename = os.path.basename(file_path)
        destination_path = os.path.join(destination_folder, filename)
        
        if os.path.exists(destination_path):
            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(os.path.join(destination_folder, f"{base}_{counter}{extension}")):
                counter += 1
            destination_path = os.path.join(destination_folder, f"{base}_{counter}{extension}")

        shutil.move(file_path, destination_path)
        logging.info(f"[Move] SUCCESS: {file_path} -> {destination_path}")
        return True
    except Exception as e:
        logging.error(f"[Move] ERROR: {e}")
        return False

# --- ЛОГІКА ПОТОКУ (WORKER) ---

def process_folder_logic(target_folder, stop_event):
    """
    Цей код працює в окремому потоці.
    Він САМ читає конфіг, щоб отримати найсвіжіші правила для своєї папки.
    """
    logging.info(f"[*] Thread started for: {target_folder}")

    while not stop_event.is_set():
        # 1. Читаємо актуальний конфіг прямо всередині циклу
        full_config_data = load_config_safe(CONFIG_PATH)
        
        my_config = None
        
        # Шукаємо налаштування саме для цієї папки
        if full_config_data:
            for entry in full_config_data:
                if isinstance(entry, list) and len(entry) >= 2:
                    if entry[0] == target_folder:
                        my_config = entry[1]
                        break
        
        # Якщо конфіг для цієї папки зник з файлу - зупиняємо потік
        if my_config is None:
            logging.info(f"[-] Config missing for {target_folder}. Stopping thread.")
            break

        # 2. Розбираємо налаштування
        settings = my_config.get("settings", {})
        rules = my_config.get("rules", [])
        
        try:
            freq = float(settings.get("frequency", 1.0))
        except:
            freq = 1.0
        
        sleep_seconds = freq * 60
        
        # Якщо вимкнено (enabled: false) - просто спимо
        if not settings.get("enabled", False):
            # Спимо короткий час, щоб швидко зреагувати на включення
            steps = 10
            for _ in range(steps):
                if stop_event.is_set(): break
                time.sleep(0.5) 
            continue

        # 3. Виконуємо роботу
        try:
            if os.path.exists(target_folder):
                files = [f for f in os.listdir(target_folder) if os.path.isfile(os.path.join(target_folder, f))]
                
                for filename in files:
                    file_path = os.path.join(target_folder, filename)
                    
                    for rule in rules:
                        criteria = rule.get("criteria") 
                        operation = rule.get("Operation") 
                        value = rule.get("Value") 
                        action = rule.get("Action") 
                        details = rule.get("Details") 
                        
                        match = False

                        # --- ПЕРЕВІРКА КРИТЕРІЇВ ---
                        
                        # Extension
                        if criteria == "Extension":
                            _, ext = os.path.splitext(filename)
                            check_val = value.lower() if value else ""
                            if not check_val.startswith("."): check_val = "." + check_val
                                
                            if operation == "equals" and ext.lower() == check_val:
                                match = True
                            elif operation == "contains" and check_val in ext.lower():
                                match = True
                        
                        # Name
                        elif criteria == "Name":
                            name_only, _ = os.path.splitext(filename)
                            check_val = value.lower() if value else ""
                            
                            if operation == "equals" and name_only.lower() == check_val:
                                match = True
                            elif operation == "contains" and check_val in name_only.lower():
                                match = True

                        # Size (MB)
                        elif criteria == "Size (MB)":
                            try:
                                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                                check_val = float(value)
                                if operation == "greater than" and size_mb > check_val: match = True
                                elif operation == "less than" and size_mb < check_val: match = True
                                elif operation == "equals" and abs(size_mb - check_val) < 0.01: match = True
                            except: pass

                        # --- ВИКОНАННЯ ДІЙ ---
                        if match:
                            if action == "Delete":
                                os.remove(file_path)
                                logging.info(f"[Delete] {filename}")
                                break 
                            elif action == "Move":
                                move_file_action(file_path, details)
                                break 
                            elif action == "Rename":
                                rename_file_with_template(file_path, details)
                                break
            else:
                logging.warning(f"Folder not found: {target_folder}")

        except Exception as e:
            logging.error(f"Error in thread {target_folder}: {e}")

        # Чекаємо наступного циклу
        steps = int(sleep_seconds)
        for _ in range(steps):
            if stop_event.is_set(): break
            time.sleep(1)
        
        if not stop_event.is_set():
            remainder = sleep_seconds - int(sleep_seconds)
            if remainder > 0:
                time.sleep(remainder)

# --- ГОЛОВНИЙ МЕНЕДЖЕР ---

def start_manager(config_path="automation_config.json"):
    """
    Ця функція викликається з інтерфейсу.
    Вона приймає шлях до файлу налаштувань.
    """
    global CONFIG_PATH
    CONFIG_PATH = config_path # Оновлюємо глобальну змінну отриманим шляхом
    
    logging.info("--- MANAGER STARTED ---")
    logging.info(f"Watching config: {os.path.abspath(CONFIG_PATH)}")

    while True:
        data = load_config_safe(CONFIG_PATH)
        
        if data is None:
            # Файл пустий або недоступний, чекаємо і пробуємо знову
            time.sleep(3)
            continue

        # Отримуємо список папок, які зараз є в JSON
        current_paths_in_json = []
        for entry in data:
            if isinstance(entry, list) and len(entry) >= 2:
                current_paths_in_json.append(entry[0])

        # 1. ЗАПУСК НОВИХ ПОТОКІВ
        for path in current_paths_in_json:
            if path not in active_threads:
                logging.info(f"[Manager] Found new folder: {path}. Starting thread.")
                stop_event = threading.Event()
                t = threading.Thread(target=process_folder_logic, args=(path, stop_event))
                t.daemon = True
                t.start()
                active_threads[path] = stop_event

        # 2. ЗУПИНКА ВИДАЛЕНИХ ПОТОКІВ
        # Якщо папка була в threads, але зникла з JSON
        paths_to_remove = []
        for running_path in active_threads:
            if running_path not in current_paths_in_json:
                logging.info(f"[Manager] Folder removed from config: {running_path}. Stopping thread.")
                active_threads[running_path].set() # Сигнал зупинки
                paths_to_remove.append(running_path)
        
        # Чистимо словник
        for p in paths_to_remove:
            del active_threads[p]

        # Головний менеджер перевіряє файл кожні 5 секунд
        time.sleep(5)