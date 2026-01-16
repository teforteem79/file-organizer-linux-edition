import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from tkinter import font as tkfont
from PIL import Image, ImageDraw 
from pystray import MenuItem as item
import threading, random, json, sys, time, pystray, os, datetime, ctypes, re, platform, shutil
import back_function as back

#region Theme Presets

bg_c = "#2B2B2B"
open_default_directory = os.path.expanduser("~") 

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for portable install """
    # 1. Check if running from the /opt/ installation
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    # 2. Return the joined path
    return os.path.join(base_path, relative_path)

# main.py

def get_config_path(filename):
    # 1. Determine where the USER's config should live (Permanent storage)
    if platform.system() == "Windows":
        user_config_dir = os.path.join(os.environ['APPDATA'], "FileOrganizer")
    else:
        # Linux standard: ~/.config/file-organizer
        user_config_dir = os.path.expanduser("~/.config/file-organizer")

    if not os.path.exists(user_config_dir):
        os.makedirs(user_config_dir, exist_ok=True)

    target_file = os.path.join(user_config_dir, filename)

    # 2. If the file doesn't exist in the permanent folder, 
    # check if we have a default one inside the App Bundle to copy over.
    if not os.path.exists(target_file):
        try:
            # Look inside the PyInstaller bundle (Temporary folder)
            bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
            default_config = os.path.join(bundle_dir, "config", filename)
            
            if os.path.exists(default_config):
                shutil.copy2(default_config, target_file)
        except Exception as e:
            print(f"Migration error: {e}")

    return target_file

#region BG funct. exec.

worker_thread = None
stop_event = threading.Event()

def periodic_zoning(stop_event, app_dir):

    CONFIG_PATH = get_config_path('desktop_config.json')
    
    while not stop_event.is_set():
        
        try:
            with open(CONFIG_PATH, "r") as f:
                desktop_config = json.load(f)
            organizer = back.CinnamonDesktopOrganizer()
            organizer.organize_desktop(desktop_config)

        except Exception as e:
            print(f"An error occured: {e}")
        
        frequency_seconds = 60 
        freq_minutes_display = 1
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                   
                    freq_minutes_display = config.get("desktop_settings", {}).get("check_frequency", 1)
                   
                    frequency_seconds = float(freq_minutes_display) * 60
            else:
                
                print(f"Файл конфігурації не знайдено, використовую {frequency_seconds} сек.")
        except Exception as e:
            print(f"Помилка читання конфігу, використовую {frequency_seconds} сек. Помилка: {e}")

        print(f"Очікую {frequency_seconds} секунд ({freq_minutes_display} хв)...")
        stop_event.wait(timeout=frequency_seconds) 
    
        
    print("Distribution by zones stopped.")


def config_manager_loop():

    global worker_thread, stop_event
    
    try:
        if getattr(sys, 'frozen', False):
            APP_DIR = os.path.dirname(sys.executable)
        else:
            APP_DIR = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        APP_DIR = os.path.abspath(".")
        
    CONFIG_PATH = get_config_path('desktop_config.json')
    
    #print(f"Фоновий менеджер запущено.")
    #print(f"Відстежую файл: {CONFIG_PATH}")
    
    last_known_enabled_state = False

    while True:
       
        is_enabled = False 
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                   
                    is_enabled = config.get("desktop_settings", {}).get("enabled", False)
            else:
               
                if last_known_enabled_state == True: 
                    print(f"Файл конфігурації не знайдено. Припускаємо 'enabled: false'.")
        except Exception as e:
            print(f"Помилка читання {CONFIG_PATH}: {e}. Припускаємо 'enabled: false'.")
            is_enabled = False

        if last_known_enabled_state != is_enabled:
             print(f"Детектор зміни стану: 'enabled' тепер {is_enabled}")
             last_known_enabled_state = is_enabled

        is_worker_running = (worker_thread is not None and worker_thread.is_alive())

        if is_enabled and not is_worker_running:
            #print("'enabled: true' виявлено. Запускаємо 'Робітника'...")
            stop_event.clear() 
            worker_thread = threading.Thread(target=periodic_zoning, args=(stop_event, APP_DIR), daemon=True)
            worker_thread.start()
        
        elif not is_enabled and is_worker_running:
            #print("'enabled: false' виявлено. Зупиняємо 'Робітника'...")
            stop_event.set() 
            worker_thread.join(timeout=3) 
            worker_thread = None

        time.sleep(5) #chek mark true/false

#region App conf.

class App(tk.Tk):
    """Main Class of the app that controlls every menu and app itself"""
    def __init__(self, *args, **kwargs):

        try:
            myappid = 'mycompany.fileorganizer.ver1.0' 
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        super().__init__(*args, **kwargs)

        try:
            self.iconbitmap(resource_path("bin/main_icon.ico"))
        except Exception:
            pass

        #   Configuring the window itself.
        self.title(back.random_window_name())
        self.geometry("1000x600")
        self.minsize(800, 500)
        self.configure(bg=bg_c)

        self.icon = None

        #   Creating the container that will hold all menus as a deck of cards.
        container = tk.Frame(self, bg=bg_c)
        container.pack(side="top", fill="both", expand=True)   #   This line of code makes frame fill whole window
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.frames = {}        #   Dictionary that assigns the name of menu to its class
        self.current_frame_name = None

        #   List of all menus that we want to use
        for F in (StartPage, SortingPage, FillerPage, RenamingMenu, LogsPage, DesktopPage, AutomationPage, SettingsMenu, VIPsPage):
            page_name = F.__name__                                          #   Getting the name of menu
            frame = F(parent=container, controller=self)                    #   Placing menu inside of container
            self.frames[page_name] = frame                                  #   Assigning name to menu
            frame.grid(row=0, column=0, sticky="nsew")                      #   Placing all menus on eachother

        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.show_frame("StartPage")

        self.setup_tray_icon()


        #region Style

        style = ttk.Style(self)
        
        #   Select a theme which we will use as a base.
        self.tk.call("source", resource_path("bin/azure.tcl"))
        self.tk.call("set_theme", "dark")
        
        style.configure("Dark.Treeview", 
                        background="#2A2D2E",
                        foreground="white",
                        fieldbackground="#3C3F41", #    Cell color
                        rowheight=25)
        
        style.map("Dark.Treeview", 
                  background=[('selected', '#1E5F8A')]) # Chosen row collor

        style.configure("Dark.Treeview.Heading",
                        background="#565A5E",
                        foreground="white",
                        relief="flat"
                        )
        
        style.map("Dark.Treeview.Heading",
                  background=[('active', '#6A6E71')])
        
        style.configure("TButton", background="#565A5E", foreground="white", font=("Sans Serif", 10))
        style.map("TButton", background=[('active', '#6A6E71')])

        observer_thread = threading.Thread(target=lambda: back.start_monitoring2(debug_mode=True), daemon=True)
        observer_thread.start()

        automation_start = threading.Thread(target=lambda: back.start_manager(get_config_path("automation_config.json")), daemon=True)
        automation_start.start()

        manager_thread = threading.Thread(target=config_manager_loop, daemon=True)
        manager_thread.start()


    def show_frame(self, page_name):
        """Gets the chosen menu up to top of container."""
        frame = self.frames[page_name]
        if self.current_frame_name:
            old_frame = self.frames[self.current_frame_name]
            if hasattr(old_frame, 'on_hide'):
                old_frame.on_hide()
        if hasattr(frame, 'on_show'):
            frame.on_show()
        frame.tkraise()
        self.current_frame_name = page_name

    def create_fallback_icon(self):
        try:
            image = Image.open(resource_path("bin/Sort.png"), "rb").read()
            return image
        except Exception:
         
            width = 64
            height = 64
            color1 = (100, 100, 255) # Синій
            color2 = (255, 255, 255) # Білий
            image = Image.new('RGB', (width, height), color1)
            dc = ImageDraw.Draw(image)
            dc.rectangle([width // 4, height // 4, width * 3 // 4, height * 3 // 4], fill=color2)
            return image

    def get_desktop_sorting_state(self, item):
        try:
            desktop_page = self.frames["DesktopPage"]
            return desktop_page.enable_sorting_var.get()
        except (KeyError, AttributeError):
            return False

    def toggle_desktop_sorting_from_tray(self, icon, item):
        try:
            desktop_page = self.frames["DesktopPage"]
            
            current_state = desktop_page.enable_sorting_var.get()
            desktop_page.enable_sorting_var.set(not current_state)
            
            desktop_page._on_toggle_sorting()
            
        except Exception as e:
            print(f"Error toggling from tray: {e}")

    def get_automation_state(self, item):
        try:
            page = self.frames["AutomationPage"]
            if not page.automation_config:
                page.load_config()
            
            for folder_data in page.automation_config:
                settings = folder_data[1].get("settings", {})
                if settings.get("enabled", False):
                    return True
            return False
        except Exception:
            return False

    def toggle_automation_from_tray(self, icon, item):
        try:
            page = self.frames["AutomationPage"]
            if not page.automation_config:
                page.load_config()

            is_any_active = self.get_automation_state(None)
            
            target_state = not is_any_active

            for folder_data in page.automation_config:
                if "settings" not in folder_data[1]:
                    folder_data[1]["settings"] = {}
                folder_data[1]["settings"]["enabled"] = target_state

            page.save_config()
            
            if page.selected_folder:
                 for item in page.automation_config:
                     if item[0] == page.selected_folder:
                         page._update_settings_ui(item[1].get("settings"))
                         break

        except Exception as e:
            print(f"Error toggling automation: {e}")

    def setup_tray_icon(self):
            # Prevent creating multiple icons if one already exists
            if hasattr(self, 'icon') and self.icon is not None:
                return

            try:
                icon_image = Image.open(resource_path("bin/main_icon.png"))
            except Exception:
                icon_image = self.create_fallback_icon()

            # Wrap tray calls in self.after(0, ...) to ensure they run on the Main Thread
            def open_page_safe(name):
                self.after(0, lambda: self.navigate_from_tray(name))

            desktop_menu = pystray.Menu(
                item('Open desktop', lambda: open_page_safe("DesktopPage")),
                item('Enable sorting', lambda: self.after(0, self.toggle_desktop_sorting_from_tray), checked=self.get_desktop_sorting_state)
            )

            automation_menu = pystray.Menu(
                item('Open автоматизацію', lambda: open_page_safe("AutomationPage")),
                item('Enable all folders', lambda: self.after(0, self.toggle_automation_from_tray), checked=self.get_automation_state)
            )

            menu = pystray.Menu(
                item('File Organizer', lambda: self.after(0, self.show_window), default=True),
                pystray.Menu.SEPARATOR,
                item('Sorting', lambda: open_page_safe("SortingPage")),
                item('Renaming', lambda: open_page_safe("RenamingMenu")),
                item('Log', lambda: open_page_safe("LogsPage")),
                item('Automatization', automation_menu),
                item('Desktop', desktop_menu),
                pystray.Menu.SEPARATOR,
                item('VIPs', lambda: open_page_safe("VIPsPage")),
                pystray.Menu.SEPARATOR,
                item('Settings', lambda: open_page_safe("SettingsMenu")),
                pystray.Menu.SEPARATOR,
                item('Exit', lambda: self.after(0, self.quit_app))
            )
            
            self.icon = pystray.Icon("FileOrganizer", icon_image, "File Organizer", menu)
            # Start the icon in a daemon thread so it doesn't block the app exit
            threading.Thread(target=self.icon.run, daemon=True).start()

    def show_window(self):
        # On Linux, DO NOT stop the icon. Just deiconify the window.
        # This prevents the tray menu from breaking.
        self.deiconify()
        self.lift()
        self.focus_force()

    def navigate_from_tray(self, page_name):
        self.show_frame(page_name)
        self.show_window()

    def hide_window(self):
        # Simply hide the window; the tray icon remains running in the background.
        self.withdraw()

    def quit_app(self):
        if hasattr(self, 'icon') and self.icon:
            self.icon.stop()
        self.destroy()
        os._exit(0) # Force exit background threads
        


#region Main Menu

class StartPage(tk.Frame):
    """Main Menu"""
    def __init__(self, parent, controller):
        super().__init__(parent, bg=bg_c)
        self.controller = controller

        self.icon_images = {}

        #   --- Labels ---
        #   Use custom fonts for better view. This is font variables that can be pasted in font
        hello_font = tkfont.Font(family="Serif", size=48, weight="bold")
        choose_font = tkfont.Font(family="Sans Serif", size=14)
        
        #   Creating frame for text.
        text_container = tk.Frame(self, bg=bg_c)
        text_container.pack(pady=(100, 50))                 #   Skipp 100 pixels from top, and leave 50 from bottom

        tk.Label(text_container, text="Hello!", font=hello_font, fg="white", bg=bg_c).pack()
        tk.Label(text_container, text="Choose an action:", font=choose_font, fg="white", bg=bg_c).pack(pady=5)


        #   --- Button frame ---
        buttons_frame = tk.Frame(self, bg=bg_c)
        buttons_frame.pack(pady=50)

        #   List of button data: (text, bg collor, menu)
        button_data = [
            ("Sort", "#F28C28", "SortingPage"),
            ("Rename", "#FDEE00", "RenamingMenu"),
            ("Logs", "#90EE90", "LogsPage"),
            ("Automatization", "#00BFFF", "AutomationPage"),
            ("VIPs", "#BF40BF", "VIPsPage"),
            ("Desktop", "#89CFF0", "DesktopPage"),
            ("Settings","#3E5568", "SettingsMenu")
        ]
        
        #   Creating buttons
        for text, color, page in button_data:

            #   Create individual frame for each button
            btn_container = tk.Frame(buttons_frame, bg=bg_c)
            btn_container.pack(side="left", padx=15, pady=10)
            
            #   Upper part is a label that will hold icon   
            icon = tk.PhotoImage(file=resource_path(f"bin/{text}.png"))
            icon = icon.subsample(2,2)                      #   Resizing image, making it 2 times small.
            
            
            #Focusing on "problem" Setting icon
            if text=="Settings":
                settings_data=(text, color, page)
                continue

            self.icon_images[text] = icon                   #   Very important. Python will clear garbage so we need to save icon
            icon_label = tk.Label(btn_container, text="", image=icon, relief="flat", borderwidth=2, bg=bg_c)
            icon_label.pack(pady=(0, 5))

            #   Bottom part with text
            text_label = tk.Label(btn_container, text=text, fg="white", bg=bg_c, font=("Sans Serif", 12))
            text_label.pack()

            #   Make the whole frame clickable
            #   Use lambda to give right name of menu
            command = lambda event, p=page: controller.show_frame(p)
            btn_container.bind("<Button-1>", command)
            icon_label.bind("<Button-1>", command)

        text, color, page = settings_data # Використовуємо збережені дані

        settings_container = tk.Frame(self, bg=bg_c)
        
        # *** ВИКОРИСТАННЯ .place() ДЛЯ ФІКСОВАНОГО ПОЗИЦІОНУВАННЯ ***
        settings_container.place(relx=1.0, rely=1.0, anchor='se', x=-10, y=-10)

        #   Upper part is a label that will hold icon   
        icon = tk.PhotoImage(file=resource_path(f"bin/{text}.png"))
        icon = icon.subsample(2,2)

        if text=="Settings":
            icon=icon.subsample(4,4)

        self.icon_images[text] = icon
        icon_label = tk.Label(settings_container, text="", image=icon, relief="flat", borderwidth=2, bg=bg_c)
        icon_label.pack(pady=(0, 5))

        #   Bottom part with text
        text_label = tk.Label(settings_container, text=text, fg="white", bg=bg_c, font=("Sans Serif", 12))
        text_label.pack()

        #   Make the whole frame clickable
        command = lambda event, p=page: controller.show_frame(p)
        settings_container.bind("<Button-1>", command)
        icon_label.bind("<Button-1>", command)


#region Placeholder
class FillerPage(tk.Frame):
    """Menu placeholder"""
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#3C3C3C")
        self.controller = controller
        
        # Menu label
        tk.Label(self, text="Placeholder", font=("Sans Serif", 20), fg="white", bg="#3C3C3C").pack(pady=50)
        
        # Return Button
        back_button = tk.Button(self, text="< Return", 
                                command=lambda: controller.show_frame("StartPage"))
        back_button.place(x=10, y=10)


#region Sorting Menu
class SortingPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=bg_c)
        self.controller = controller
        self.file_data = []
        self.all_columns = []
        self.source_folder_path = None
        self.first_launch = True

        self.profiles_file = get_config_path("sorting_profiles.json")

        

        #   --- Top button pannel ---
        top_panel = tk.Frame(self, bg="#3C3F41")
        top_panel.pack(side="top", fill="x", padx=10, pady=10)

        folder_button = ttk.Button(top_panel, text="Folder", command=self.load_folder_data)
        folder_button.pack(side="left", padx=5, pady=5)

        reset_button = ttk.Button(top_panel, text="Reset", command=self._reset_page)
        reset_button.pack(side="left", padx=5, pady=5)
        
        return_button = ttk.Button(top_panel, text="Return", command=lambda: controller.show_frame("StartPage"))
        return_button.pack(side="right", padx=5, pady=5)

        ttk.Button(top_panel, text="Save New", command=self._save_profile).pack(side="left", padx=(20, 2))

        self.profile_var = tk.StringVar()
        self.profile_combo = ttk.Combobox(top_panel, textvariable=self.profile_var, state="readonly", width=15)
        self.profile_combo.pack(side="left", padx=2)
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_select)

        self.btn_change_profile = ttk.Button(top_panel, text="Overwrite", command=self._overwrite_profile, state="disabled")
        self.btn_change_profile.pack(side="left", padx=2)

        self.btn_delete_profile = ttk.Button(top_panel, text="Delete", command=self._delete_profile, state="disabled")
        self.btn_delete_profile.pack(side="left", padx=2)

        self._refresh_profiles_list()

        #   --- Main Content Frame ---
        content_frame = tk.Frame(self, bg=bg_c)
        content_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        #   Left column for Table
        tree_frame = tk.Frame(content_frame, bg=bg_c)
        tree_frame.pack_propagate(False)
        tree_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        #   Midle column for Folder Sctructure
        middle_frame = tk.Frame(content_frame, bg=bg_c)
        middle_frame.pack_propagate(False)
        middle_frame.pack(side="left", fill="both", expand=True, padx=(5, 5))

        #   Right column for group rules
        right_frame = tk.Frame(content_frame, bg=bg_c)
        right_frame.pack_propagate(False)
        right_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

        #   --- LEFT COLUMN ---
        self.tree = ttk.Treeview(tree_frame, show='headings', style="Dark.Treeview")
        #   Scrollbars              !!!!!!!!!! Make horizontal Scrollbar go faster 
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)     #   Vertical Scrollbar
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)   #   Horizontal Scrollbar
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.tree.pack(side='left', fill='both', expand=True)
        #   Binding right click for column choosing
        self.tree.heading("#0", text="", anchor="w")            # Hidden first column
        self.tree.bind("<Button-3>", self.show_header_menu)
        self.tree['columns'] = []
        self.tree['displaycolumns'] = []

        #   --- MIDLE COLUMN ---
        self.midle_panel = FolderTreeView(middle_frame)
        self.midle_panel.pack(fill="both", expand=True)

        #   --- RIGHT COLUMN ---
        self.groups_manager = GroupsManager(right_frame, 
                                            folder_tree_view=self.midle_panel,
                                            file_tree=self.tree,
                                            file_data_source=self.file_data) 
        self.groups_manager.pack(fill="both", expand=True)
        start_button = ttk.Button(right_frame, text="Start Sorting", command=self.start_sorting_process, style="Red.TButton")
        start_button.pack(side="bottom", fill="x", pady=5, padx=5)

    #region Table
    def load_folder_data(self):
        """Get data from folder and populate table"""
        folder = filedialog.askdirectory(initialdir=open_default_directory)
        if not folder:
            return                                  #   If no folder selected - stop
        elif back.is_system_path_prohibited(folder) == True:
            messagebox.showerror('Access Prohibited', 'System Folder Detected, operation terminated.')
            return

        self.file_data.clear()                      #   Clear previous info

        self.source_folder_path = folder
        self.midle_panel.set_default_output_path(folder)
        
        file_paths = back.open_folder(folder)       #   Get all files from folder
        
        for path in file_paths:
            info = back.get_file_info(path)
            if info:
                self.file_data.append(info)         #   Get info of every file given
        
        self.populate_treeview()                    #   Fill Table

    def populate_treeview(self):
        """Dinamicly creating column and filling table"""
        previous_display_columns = list(self.tree["displaycolumns"])

        self.tree.delete(*self.tree.get_children())

        if not self.file_data:
            self.tree["displaycolumns"] = []
            self.tree["columns"] = []
            return

        all_keys = set()
        for item in self.file_data:
            all_keys.update(item.keys())
        priority = ['Full Name', 'Name', 'Extension', 'Size', 'Path']
        self.all_columns = sorted(list(all_keys), key=lambda x: (x not in priority, priority.index(x) if x in priority else 0))

        if not previous_display_columns:
            display_cols = ["Name", "Extension"]
        else:
            display_cols = [col for col in previous_display_columns if col in self.all_columns]

        
        self.tree["displaycolumns"] = []

        self.tree["columns"] = self.all_columns

        self.tree["displaycolumns"] = display_cols
        

        #   Creating Headings
        for col in self.all_columns:
            self.tree.heading(col, text=col, anchor='w', 
                              command=lambda c=col: self.sort_column(c, False))
            self.tree.column(col, width=150, anchor='w', stretch=False)

        #   Fill in the data
        for item in self.file_data:
            values = [item.get(col, "") for col in self.all_columns]
            self.tree.insert("", "end", values=values)

    def sort_column(self, col, reverse):
        """Sort data in Table by given column"""
        #   Get data to sort
        data_to_sort = []
        for item in self.file_data:
            data_to_sort.append((item.get(col, ""), item))

        #   Sorting
        data_to_sort.sort(key=lambda x: x[0], reverse=reverse)
        
        #   Update file_data with sorted data
        self.file_data = [item[1] for item in data_to_sort]
        
        #   Refill the table
        self.populate_treeview()
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def show_header_menu(self, event):
        """Show Context Menu for enabling and disabling columns"""
        #   Get if the needed area is clicked
        if self.tree.identify_region(event.x, event.y) != "heading":
            return

        menu = tk.Menu(self, tearoff=0)     #   Context Menu
        
        #   Create variants for each column
        for col in self.all_columns:
            var = tk.BooleanVar()                                       #   Assign a boollean field
            var.set(col in self.tree["displaycolumns"])                 #   Make columns that are displayed right now - have a positive boollean
            menu.add_checkbutton(label=col, variable=var,               #   Write a row into the menu
                                command=lambda v=var, c=col: self.toggle_column(v, c))

        menu.post(event.x_root, event.y_root)

    def toggle_column(self, var, col_name):
        """Hide or show column"""
        current_display = list(self.tree["displaycolumns"])                     #   Get what column are displayed right now
        if var.get():                                                   #   If flag is True
            if col_name not in current_display:
                insert_pos = self.all_columns.index(col_name)                   #   Insert column in it`s original position
                current_display.insert(insert_pos, col_name)
                current_display.sort(key=lambda c: self.all_columns.index(c))   #   Sort to retreave right view
        else:                                                           #   If flag is false
            if col_name in current_display:
                current_display.remove(col_name)                                #   Remove column
        
        self.tree["displaycolumns"] = current_display

    def _reset_page(self):
        """Clear all data"""
        confirm = messagebox.askyesno(
            title="Confirm Reset", 
            message="Are you sure you want to clear all loaded files, folder structures, and groups?\nThis action cannot be undone."
        )
        if confirm:
            self.tree.delete(*self.tree.get_children())
            self.file_data.clear()
            self.tree["displaycolumns"] = []
            self.tree["columns"] = []
            self.first_launch = True

            if hasattr(self, 'midle_panel'):
                self.midle_panel.clear_view()
            if hasattr(self, 'groups_manager'):
                self.groups_manager.clear_view()

            self.source_folder_path = None
            
            messagebox.showinfo("Reset", "The sorting page has been cleared.", parent=self)

    def start_sorting_process(self):
        """Start sorting procces"""
        #   Get folder structure
        folder_structure = self.midle_panel.get_folder_structure_as_list()
        
        #   Check if root folder is selected
        if folder_structure is None:
            return
        
        groups = self.groups_manager.get_groups()
        
        if not groups:
            messagebox.showwarning("Warning", "No sorting groups created.", parent=self)
            return
            
        print("Structure that will be given to backend:", folder_structure)
        print("Groups to process:", groups)
        
        #   Start sorting
        back.StartSorting(folder_structure, self.source_folder_path, groups, self.file_data)
    
    def _toggle_profile_buttons(self, enable):
        """Turns delete profile on and off"""
        state = "normal" if enable else "disabled"
        self.btn_change_profile.config(state=state)
        self.btn_delete_profile.config(state=state)

    def _refresh_profiles_list(self):
        """Refresh profile list"""
        profiles = back.reading_profs(debug=False, path=self.profiles_file)
        profile_names = ["Custom"] + list(profiles.keys()) if profiles else ["Custom"]
        self.profile_combo['values'] = profile_names
        
        current_val = self.profile_combo.get()
        if not current_val or current_val not in profile_names:
            self.profile_combo.set("Custom")
            self._toggle_profile_buttons(False)
        else:
            self._toggle_profile_buttons(current_val != "Custom")

    def _save_profile(self):
        """Save current settings as new profile"""
        profile_name = simpledialog.askstring("Save Profile", "Enter NEW profile name:", parent=self)
        if not profile_name: return
        if profile_name == "Custom":
            messagebox.showwarning("Invalid Name", "'Custom' is reserved.", parent=self)
            return

        # Перевірка на існування
        current_profiles = back.reading_profs(debug=False, path=self.profiles_file) or {}
        if profile_name in current_profiles:
            if not messagebox.askyesno("Overwrite?", f"Profile '{profile_name}' exists. Overwrite?"):
                return

        self._write_profile_to_disk(profile_name, current_profiles)

    def _overwrite_profile(self):
        """Change CURRENT selecter profile"""
        profile_name = self.profile_combo.get()
        if profile_name == "Custom" or not profile_name:
            return

        if messagebox.askyesno("Confirm Overwrite", f"Update profile '{profile_name}' with current settings?", parent=self):
            current_profiles = back.reading_profs(debug=False, path=self.profiles_file) or {}
            self._write_profile_to_disk(profile_name, current_profiles)

    def _delete_profile(self):
        """Видаляє поточний профіль."""
        profile_name = self.profile_combo.get()
        if profile_name == "Custom": return

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete profile '{profile_name}'?", parent=self):
            current_profiles = back.reading_profs(debug=False, path=self.profiles_file) or {}
            if profile_name in current_profiles:
                del current_profiles[profile_name]
                if back.writing_profs(self.profiles_file, current_profiles, debug=False):
                    self._refresh_profiles_list()
                    self.profile_combo.set("Custom")
                    self._toggle_profile_buttons(False)
                    messagebox.showinfo("Deleted", f"Profile '{profile_name}' deleted.")
    
    def _write_profile_to_disk(self, name, all_profiles):
        """Helper function"""
        tree_data = self.midle_panel.folder_tree_data
        groups_data = self.groups_manager.groups
        
        profile_data = {
            "folder_tree": tree_data,
            "groups": groups_data
        }
        all_profiles[name] = profile_data
        
        if back.writing_profs(self.profiles_file, all_profiles, debug=False):
            self._refresh_profiles_list()
            self.profile_combo.set(name)
            self._toggle_profile_buttons(True)
            messagebox.showinfo("Success", f"Profile '{name}' saved.")
        else:
            messagebox.showerror("Error", "Failed to save profile.")

    def _on_profile_select(self, event):
        """Load chosen profile"""
        selected_profile = self.profile_combo.get()
        
        if selected_profile == "Custom":
            return

        confirm = messagebox.askyesno(
            "Load Profile", 
            f"Do you want to overwrite current settings and load profile '{selected_profile}'?",
            parent=self
        )
        
        if not confirm:
            self.profile_combo.set("Custom") 
            return

        all_profiles = back.reading_profs(debug=False, path=self.profiles_file)
        profile_data = all_profiles.get(selected_profile)

        if not profile_data:
            messagebox.showerror("Error", "Profile data not found.")
            return

        try:
            self.midle_panel.folder_tree_data = profile_data.get("folder_tree", {})
            self.midle_panel.update_view()

            self.groups_manager.groups = profile_data.get("groups", [])
            self.groups_manager._refresh_listbox()
            
            self.midle_panel.output_root_path = None
            self.midle_panel.path_label.config(text="Output Folder: Not Selected")

            self._toggle_profile_buttons(True)
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load profile: {e}")
            self.profile_combo.set("Custom")


#region Folder creation
class FolderTreeView(ttk.Frame):
    """Vidget for visual folder ctructure creation in form of classic tree"""
    def __init__(self, parent):
        super().__init__(parent, style="TFrame")
        
        #   --- Data Module ---
        self.folder_tree_data = {}          #   Dictionaru to save structure
        self.output_root_path = None
        self.default_output_path = None

        #   --- UI Components ---
        #   Main buttons panel
        control_frame = ttk.Frame(self)
        control_frame.pack(side="top", fill="x", pady=(0, 10))

        self.path_label = ttk.Label(control_frame, text="Output Folder: Not Selected", anchor="w")      #   Label that shows path that folders will be creared
        self.path_label.pack(side="left", fill="x", expand=True, padx=5)

        select_path_btn = ttk.Button(control_frame, text="Select Root...", command=self.select_root_path)   #   Button to choose root folder
        select_path_btn.pack(side="right", padx=5)
        
        #   --- Treeview and scrollbar creation ---
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(tree_frame, show="tree headings", style="Dark.Treeview")
        self.tree.pack(side="left", fill="both", expand=True)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=vsb.set)
        
        #   Config the header
        self.tree.heading("#0", text="Folder Structure")
        
        #   Bind right click to context menu
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.update_view()

    def get_root_path(self):
        """Return the root path"""
        return self.output_root_path if self.output_root_path is not None else self.default_output_path

    def get_defined_folder_paths(self):
        """
        Safely returns list of all path
        Do not need root folder. UI use only.
        """
        paths = []
        self._build_relative_paths("", self.folder_tree_data, paths)
        return paths

    def _build_relative_paths(self, parent_path, current_dict, paths_list):
        """Recursivly build relative path"""
        for name, sub_dict in current_dict.items():                             #   Current dictionary is dictionary of folders that
            current_path = f"{parent_path}/{name}" if parent_path else name     #   contain other dictionaries of other folders
            paths_list.append(current_path)                                     #   Current_path - parent folder, sub_dict - children folders
            if sub_dict:
                self._build_relative_paths(current_path, sub_dict, paths_list)

    def set_default_output_path(self, path):
        """Set default path that is given by main window"""
        self.default_output_path = path

        #   Update label BUT only if user haven`t chosen a root path already
        if not self.output_root_path:
            self.path_label.config(text=f"Default Output: {os.path.basename(path)[-10:]}")

    def show_context_menu(self, event):
        """Create and show context menu depending on where we click"""
        menu = tk.Menu(self, tearoff=0)
        
        #   Get what element was clicked
        iid = self.tree.identify_row(event.y)

        if iid:
            #   If clicked on existing folder - highlight it
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            #   Create options to work with folder
            menu.add_command(label="Add Subfolder", command=self.add_subfolder)
            menu.add_command(label="Rename", command=self.rename_folder)
            menu.add_separator()
            menu.add_command(label="Delete", command=self.delete_folder)
        else:
            #   If clicked empty space - suggest creating root folder
            menu.add_command(label="Add Root Folder", command=self.add_root_folder)
        
        menu.post(event.x_root, event.y_root)

    def _get_path_from_iid(self, iid):
        """Get path to element and his ID."""
        path = []
        while iid:
            path.insert(0, self.tree.item(iid, "text"))
            iid = self.tree.parent(iid)
        return path

    def add_root_folder(self):
        name = simpledialog.askstring("New Root Folder", "Enter name:")
        if name and name not in self.folder_tree_data:                  #   Check if folder is not existing already
            self.folder_tree_data[name] = {}
            self.update_view()

    def add_subfolder(self):
        selected_iid = self.tree.focus()
        if not selected_iid: return

        name = simpledialog.askstring("New Subfolder", "Enter name:")
        if not name: return

        path = self._get_path_from_iid(selected_iid)                    #   Get path to the folder we create new one in
        target_dict = self.folder_tree_data
        for part in path:
            target_dict = target_dict[part]                             #   Recreating branch
        
        if name not in target_dict:                                     #   Check if folder is not existing already
            target_dict[name] = {}
            self.update_view()

    def rename_folder(self):
        selected_iid = self.tree.focus()
        if not selected_iid: return

        path = self._get_path_from_iid(selected_iid)
        old_name = path[-1]                                             #   Get old name
        
        new_name = simpledialog.askstring("Rename Folder", "Enter new name:", initialvalue=old_name)
        if not new_name or new_name == old_name: return                 #   If no new name was given or it`s not different

        #   Find parent dictionary
        parent_dict = self.folder_tree_data
        for part in path[:-1]:
            parent_dict = parent_dict[part]

        if new_name not in parent_dict:
            parent_dict[new_name] = parent_dict.pop(old_name)
            self.update_view()

    def delete_folder(self):
        selected_iid = self.tree.focus()
        if not selected_iid: return
        
        path = self._get_path_from_iid(selected_iid)
        
        #   Find parent dictionary
        parent_dict = self.folder_tree_data
        for part in path[:-1]:
            parent_dict = parent_dict[part]
            
        del parent_dict[path[-1]]
        self.update_view()

    def update_view(self):
        """Rebuild the tree using self.folder_tree_data"""
        self.tree.delete(*self.tree.get_children())
        self._populate_tree("", self.folder_tree_data)

    def _populate_tree(self, parent_iid, data_dict):
        """Recursivly fill tree with data from dictionary"""
        for name, sub_dict in sorted(data_dict.items()):
            #   Create new element
            iid = self.tree.insert(parent_iid, "end", text=name, open=True)
            #   Recursivly call this function for children
            self._populate_tree(iid, sub_dict)

    def select_root_path(self):
        """Opens dialoge to choose root folder"""
        path = filedialog.askdirectory(initialdir=open_default_directory)
        if path:
            self.output_root_path = path
            if len(path) >=15:
                self.path_label.config(text=f"Output Folder: ...{path[-13:]}")
            else:
                self.path_label.config(text=f"Output Folder: {path}")

    def get_folder_structure_as_list(self):
        """
        Main method for exporting data.
        Return the data in form of list for backend to work with it.
        """
        root_path = self.output_root_path if self.output_root_path is not None else self.default_output_path

        if not root_path:
            messagebox.showwarning("Path Not Found", "Please select a source folder for files or an explicit output folder.")
            return None
        
        result_list = []
        #   Start recursive run
        self.build_path_list(root_path, self.folder_tree_data, result_list)
        return result_list
            
    def build_path_list(self, parent_path, current_dict, result_list):
        """Support funtion for checking tree"""
        for name, sub_dict in current_dict.items():
            full_path = os.path.join(parent_path, name)
            
            result_list.append((name, parent_path))         #   Save name and parent folder
            
            #   Continue check for further layers
            if sub_dict:
                self.build_path_list(full_path, sub_dict, result_list)

    def clear_view(self):
        """Clear out the folder structure frame"""
        self.folder_tree_data = {}
        self.output_root_path = None
        self.default_output_path = None
        self.path_label.config(text="Output Folder: Not Selected")
        self.update_view()


#region Group Editor

class GroupEditorDialog(tk.Toplevel):
    """
    Pop-up window for creating and editing groups.
    Adapts UI based on available file metadata.
    """
    def __init__(self, parent, available_folders, file_data_list=None, group_to_edit=None, root_path=None):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Group Editor")

        self.result = None
        self.available_folders = available_folders
        self.root_path = root_path
        self.criteria_rows = []
        
        # Зберігаємо дані про файли для аналізу унікальних значень
        # file_data_list - це список словників з метаданими
        self.file_data_list = file_data_list if file_data_list else []
        
        # Формуємо список доступних критеріїв
        # 1. Стандартні (завжди є)
        base_criteria = ["Extension", "Name", "Size", "Created"]
        # 2. Додаємо ті, що знайшли у файлах
        found_criteria = set()
        for item in self.file_data_list:
            found_criteria.update(item.keys())
        
        # Видаляємо службові поля, які не є метаданими для сортування
        ignored_fields = {'Path', 'Directory', 'Full Name'}
        found_criteria = found_criteria - ignored_fields
        
        # Об'єднуємо, зберігаючи порядок важливих
        self.available_criteria = base_criteria + sorted(list(found_criteria - set(base_criteria)))


        #   --- Main Fields ---
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        ttk.Label(main_frame, text="Group Name:").grid(row=0, column=0, sticky="w", pady=2)
        self.name_entry = ttk.Entry(main_frame, width=40)
        self.name_entry.grid(row=0, column=1, columnspan=2, sticky="ew", pady=2)

        ttk.Label(main_frame, text="Destination:").grid(row=1, column=0, sticky="w", pady=2)
        self.dest_combo = ttk.Combobox(main_frame, values=self.available_folders)
        self.dest_combo.grid(row=1, column=1, sticky="ew", pady=2)
        ttk.Button(main_frame, text="Browse...", command=self._browse_folder).grid(row=1, column=2, sticky="w", padx=5)

        #   --- Criteria redactor ---
        ttk.Label(main_frame, text="Criteria:", font=("Sans Serif", 10, "bold")).grid(row=2, column=0, sticky="w", pady=(10, 5))
        self.criteria_frame = ttk.Frame(main_frame)
        self.criteria_frame.grid(row=3, column=0, columnspan=3, sticky="ew")
        ttk.Button(main_frame, text="+ Add Criterion", command=lambda: self._add_criterion_row()).grid(row=4, column=0, columnspan=3, pady=5)

        #   --- Control buttons ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=5, column=0, columnspan=3, pady=(10, 0))
        ttk.Button(btn_frame, text="Save", command=self._on_save, style="Red.TButton").pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right")
        
        if group_to_edit:
            self._load_group_data(group_to_edit)
        else:
            self._add_criterion_row()

        self.wait_window()

    def _browse_folder(self):
        path = filedialog.askdirectory(initialdir=open_default_directory)
        if path:
            self.dest_combo.set(path)

    def _get_unique_values_for_field(self, field_name):
        """Повертає список унікальних значень для певної колонки з завантажених файлів."""
        values = set()
        for item in self.file_data_list:
            val = item.get(field_name)
            if val is not None:
                values.add(str(val))
        return sorted(list(values))

    def _add_criterion_row(self, criterion_data=None):
        row_frame = ttk.Frame(self.criteria_frame)
        row_frame.pack(fill="x", pady=2)

        # 1. Критерій (Дропдаун з усіма доступними метаданими)
        field_combo = ttk.Combobox(row_frame, values=self.available_criteria, width=15, state="readonly")
        field_combo.pack(side="left", padx=2)
        
        # 2. Оператор
        op_combo = ttk.Combobox(row_frame, width=10, state="readonly")
        op_combo.pack(side="left", padx=2)

        # 3. Значення (Контейнер для динамічних віджетів)
        val_container = ttk.Frame(row_frame)
        val_container.pack(side="left", fill="x", expand=True, padx=2)

        remove_btn = ttk.Button(row_frame, text="-", width=2, command=lambda rf=row_frame: self._remove_criterion_row(rf))
        remove_btn.pack(side="left", padx=2)

        # Структура для зберігання посилань
        row_struct = {
            'frame': row_frame, 
            'field': field_combo, 
            'op': op_combo, 
            'val_container': val_container,
            'val_widgets': []
        }
        self.criteria_rows.append(row_struct)

        # Прив'язка: при зміні критерію перебудовуємо UI рядка
        field_combo.bind("<<ComboboxSelected>>", lambda e, r=row_struct: self._update_row_ui(r))

        # Заповнення даними (якщо редагуємо)
        if criterion_data:
            # Відновлюємо ім'я поля
            # (Бекенд може використовувати інші імена, тут треба мапити назад якщо треба)
            field_name = criterion_data.get('field', 'Extension')
            if field_name == "Created (Days)": field_name = "Created" # Адаптація назад
            
            field_combo.set(field_name)
            self._update_row_ui(row_struct) # Створюємо віджети
            
            op_combo.set(criterion_data.get('operator', 'equals'))
            
            print(criterion_data)
            val = criterion_data.get('value', '')
            if field_name == "Size":
                 if row_struct['val_widgets']:
                     try:
                        row_struct['val_widgets'][0].insert(0, val[0])
                        row_struct['val_widgets'][1].set(val[1])
                     except:
                         row_struct['val_widgets'][0].insert(0, val)
            elif field_name == "Created" or field_name == "Accessed" or field_name == "Modified":
                if row_struct['val_widgets']:
                    try:
                        print(val)
                        row_struct['val_widgets'][0].insert(0, val[0])
                        row_struct['val_widgets'][1].insert(1, val[1])
                        row_struct['val_widgets'][2].insert(2, val[2])
                    except:
                        row_struct['val_widgets'][0].insert(0, val)
            else:
                if row_struct['val_widgets']:
                    # Для дропдаунів
                    if isinstance(row_struct['val_widgets'][0], ttk.Combobox):
                        row_struct['val_widgets'][0].set(val)
                    # Для Entry
                    elif isinstance(row_struct['val_widgets'][0], ttk.Entry):
                         row_struct['val_widgets'][0].insert(0, val)
        else:
            # Дефолтний стан
            field_combo.set("Extension")
            self._update_row_ui(row_struct)

    def _update_row_ui(self, row_struct):
        """
        Головна функція "розумного" інтерфейсу.
        Визначає, які віджети показати для обраного критерію.
        """
        crit = row_struct['field'].get()
        container = row_struct['val_container']
        
        # Очищення старих віджетів
        for w in container.winfo_children(): w.destroy()
        row_struct['val_widgets'] = []

        # === 1. EXTENSION (Підготовлений) ===
        if crit in ["Extension", "Color Space", "Codec", "Audio Codec", "Compression", "Resolution", "Aspect Ratio", "Mode"]:
            row_struct['op']['values'] = ["equals"]
            row_struct['op'].set("equals")
            
            unique_exts = self._get_unique_values_for_field(crit)
            if not unique_exts:
                unique_exts = ["None"]
            
            val = ttk.Combobox(container, width=10, values=unique_exts)
            val.pack(fill="x")
            row_struct['val_widgets'] = [val]

        # === 2. SIZE (Підготовлений) ===
        elif crit in ["Size"]:
            row_struct['op']['values'] = ["greater than", "less than"]
            row_struct['op'].set("greater than")
            
            num = ttk.Entry(container, width=6)
            num.pack(side="left")
            unit = ttk.Combobox(container, width=4, values=["KB", "MB", "GB"], state="readonly")
            unit.set("MB")
            unit.pack(side="left")
            row_struct['val_widgets'] = [num, unit]

        elif crit in ["Length"]:
            row_struct['op']['values'] = ["greater than", "less than"]
            row_struct['op'].set("greater than")
            
            num = ttk.Entry(container, width=6)
            num.pack(side="left")
            row_struct['val_widgets'] = [num]

        elif crit in ["GPS Latitude", "GPS Longitude", "Framerate"]:
            row_struct['op']['values'] = ["greater than", "less than", "equals"]
            row_struct['op'].set("greater than")
            
            val = ttk.Entry(container)
            val.pack(fill="x")
            row_struct['val_widgets'] = [val]

        # === 3. CREATED / DATE (Підготовлений) ===
        elif crit == "Created" or crit == "Accessed" or crit == "Modified":
            row_struct['op']['values'] = ["greater than", "less than", "equals"]
            row_struct['op'].set("greater than")
            
            days = ttk.Entry(container, width=5)
            days.pack(side="left")
            lbl1 = ttk.Label(container, text="-")
            lbl1.pack(side="left")
            month = ttk.Entry(container, width=5)
            month.pack(side="left")
            lbl2 = ttk.Label(container, text="-")
            lbl2.pack(side="left")
            year = ttk.Entry(container, width=10)
            year.pack(side="left")
            row_struct['val_widgets'] = [days, month, year]

        # === 4. NAME (Підготовлений) ===
        elif crit == "Name":
            row_struct['op']['values'] = ["equals", "contains", "starts with", "ends with"]
            row_struct['op'].set("contains")
            val = ttk.Entry(container)
            val.pack(fill="x")
            row_struct['val_widgets'] = [val]

        # === 6. FALLBACK (Для всіх інших невідомих метаданих) ===
        else:
            # Стандартний набір
            row_struct['op']['values'] = ["equals", "contains", "greater than", "less than"]
            row_struct['op'].set("equals")
            
            # Перевіряємо, чи є унікальні значення (якщо їх мало, робимо дропдаун)
            unique_vals = self._get_unique_values_for_field(crit)
            if len(unique_vals) > 0:
                val = ttk.Combobox(container, width=15, values=unique_vals)
            else:
                val = ttk.Entry(container)
            
            val.pack(fill="x")
            row_struct['val_widgets'] = [val]

    def _remove_criterion_row(self, row_frame):
        self.criteria_rows = [row for row in self.criteria_rows if row['frame'] != row_frame]
        row_frame.destroy()

    def _load_group_data(self, group):
        self.name_entry.insert(0, group['name'])
        self.dest_combo.set(group['destination'])
        for c in group['criteria']:
            self._add_criterion_row(c)

    def _on_save(self):
        name = self.name_entry.get().strip()
        destination = self.dest_combo.get().strip()
        final_destination = destination

        if self.root_path and not os.path.isabs(destination):
            final_destination = os.path.join(self.root_path, destination)

        if not name or not destination:
            messagebox.showwarning("Input Error", "Group Name and Destination cannot be empty.", parent=self)
            return

        criteria_list = []
        for row in self.criteria_rows:
            field_ui = row['field'].get()
            op = row['op'].get()
            
            # Збір та конвертація значення для бекенду
            value = ""
            field_backend = field_ui
            
            # Спеціальна обробка для Size
            if field_ui == "Size":
                try:
                    num = float(row['val_widgets'][0].get())
                    unit = row['val_widgets'][1].get()
                    value = [num, unit]
                    field_backend = "Size"
                except: continue
                
            elif field_ui == "Created":
                value = [row['val_widgets'][0].get(), row['val_widgets'][1].get(), row['val_widgets'][2].get()]
                field_backend = "Created"
            elif field_ui == "Accessed":
                value = [row['val_widgets'][0].get(), row['val_widgets'][1].get(), row['val_widgets'][2].get()]
                field_backend = "Accessed"
            elif field_ui == "Modified":
                value = [row['val_widgets'][0].get(), row['val_widgets'][1].get(), row['val_widgets'][2].get()]
                field_backend = "Modified"
            else:
                if row['val_widgets']:
                    value = row['val_widgets'][0].get()

            if field_backend and op and value:
                criteria_list.append({'field': field_backend, 'operator': op, 'value': value})
        
        self.result = {'name': name, 'destination': final_destination, 'criteria': criteria_list}
        self.destroy()

#region Group Manager
class GroupsManager(ttk.Frame):
    """Group Panel"""
    def __init__(self, parent, folder_tree_view, file_tree, file_data_source):
        super().__init__(parent, style="TFrame")
        self.folder_tree_view = folder_tree_view
        self.file_tree = file_tree
        self.file_data_source = file_data_source # <--- Нове посилання на дані файлів
        self.groups = []

        # ... (код створення UI: listbox, btn_frame тощо залишається БЕЗ ЗМІН) ...
        list_frame = ttk.Frame(self)
        list_frame.pack(fill="both", expand=True, padx=5, pady=5)

        vsb = ttk.Scrollbar(list_frame, orient="vertical")
        hsb = ttk.Scrollbar(list_frame, orient="horizontal")

        self.listbox = tk.Listbox(list_frame, bg="#3C3F41", fg="white", selectbackground="#1E5F8A", 
                                  borderwidth=0, highlightthickness=0,
                                  yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.config(command=self.listbox.yview)
        hsb.config(command=self.listbox.xview)

        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.listbox.pack(fill="both", expand=True)
        
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", padx=5)
        
        ttk.Button(btn_frame, text="Add", width=3, command=self._add_group).pack(side="left", expand=True, fill="x")
        ttk.Button(btn_frame, text="Edit", width=3, command=self._edit_group).pack(side="left", expand=True, fill="x")
        ttk.Button(btn_frame, text="Delete",width=3, command=self._delete_group).pack(side="left", expand=True, fill="x")
        ttk.Button(btn_frame, text="↑", width=3, command=self._move_up).pack(side="left")
        ttk.Button(btn_frame, text="↓", width=3, command=self._move_down).pack(side="left")

    # ... (метод _refresh_listbox залишається БЕЗ ЗМІН) ...
    def _refresh_listbox(self):
        self.listbox.delete(0, "end")
        for group in self.groups:
            dest_folder = os.path.basename(group['destination']) if group['destination'] else "N/A"
            criteria_fields = [c['field'] for c in group['criteria']]
            if criteria_fields:
                rules_text = f"by {', '.join(sorted(list(set(criteria_fields))))}"
            else:
                rules_text = "no rules"
            summary_text = f"{group['name']}  ->  '{dest_folder}' ({rules_text})"
            self.listbox.insert("end", summary_text)

    def _add_group(self):
        folder_paths = self.folder_tree_view.get_defined_folder_paths()
        root_path = self.folder_tree_view.get_root_path()
        
        # Отримуємо актуальні дані про файли з SortingPage
        # file_data_list - це список словників
        file_data_list = self.file_data_source 

        dialog = GroupEditorDialog(self, 
                                   available_folders=folder_paths, 
                                   file_data_list=file_data_list, # Передаємо дані
                                   root_path=root_path)
        if dialog.result:
            self.groups.append(dialog.result)
            self._refresh_listbox()

    def _edit_group(self):
        selection = self.listbox.curselection()
        if not selection: return
        
        index = selection[0]
        group_to_edit = self.groups[index]
        
        folder_paths = self.folder_tree_view.get_defined_folder_paths()
        root_path = self.folder_tree_view.get_root_path()
        file_data_list = self.file_data_source 
        
        dialog = GroupEditorDialog(self, 
                                   available_folders=folder_paths, 
                                   group_to_edit=group_to_edit, 
                                   file_data_list=file_data_list, # Передаємо дані
                                   root_path=root_path)
        if dialog.result:
            self.groups[index] = dialog.result
            self._refresh_listbox()
            
    # ... (решта методів _delete_group, _move_up, _move_down, get_groups, clear_view залишаються БЕЗ ЗМІН) ...
    def _delete_group(self):
        selection = self.listbox.curselection()
        if not selection: return
        self.groups.pop(selection[0])
        self._refresh_listbox()

    def _move_up(self):
        selection = self.listbox.curselection()
        if not selection or selection[0] == 0: return
        index = selection[0]
        self.groups.insert(index - 1, self.groups.pop(index))
        self._refresh_listbox()
        self.listbox.selection_set(index - 1)
        
    def _move_down(self):
        selection = self.listbox.curselection()
        if not selection or selection[0] == len(self.groups) - 1: return
        index = selection[0]
        self.groups.insert(index + 1, self.groups.pop(index))
        self._refresh_listbox()
        self.listbox.selection_set(index + 1)
        
    def get_groups(self):
        return self.groups
    
    def clear_view(self):
        self.groups = []
        self._refresh_listbox()

#region Log Page
class LogsSettings(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Logs Menu Settings")
        self.logsSettings_path = back.monitoringSettings_path

        self.thr_limit_atr = back.THROTTLE_LIMIT ###НА JSON
        self.mute_duration_atr = back.MUTE_DURATION ###НА JSON
        self.mutedpaths_list = back.SYSTEM_PATHS.copy()
        self.mutedext_list = back.SYSTEM_EXTENSIONS.copy()

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)

        thr_frame = ttk.Frame(main_frame)
        thr_frame.pack(side='top', fill='x')

        vcmd = (self.register(self.validate_on_key), '%P')
        ttk.Label(thr_frame, text="Throttle Limit: ").grid(row=0, column=0, sticky="w", pady=2)
        self.thr_limit_entry = ttk.Entry(thr_frame, width=20, validate="key", validatecommand=vcmd)
        self.thr_limit_entry.grid(row=0, column=1, sticky="ew", pady=2)
        self.thr_limit_entry.insert(0, self.thr_limit_atr) ###

        ttk.Label(thr_frame, text="Mute Duration: ").grid(row=1, column=0, sticky="w", pady=2)
        self.mute_duration_entry = ttk.Entry(thr_frame, width=20, validate="key", validatecommand=vcmd)
        self.mute_duration_entry.grid(row=1, column=1, sticky="ew", pady=2)
        self.mute_duration_entry.insert(0, self.mute_duration_atr) ###


        tables_container = ttk.Frame(main_frame)
        tables_container.pack(side="top", fill="y", expand=False, pady=20)

        left_table_frame = ttk.Frame(tables_container)
        left_table_frame.pack(side="left", fill="y", expand=True, padx=(0, 10))

        path_vsb = ttk.Scrollbar(left_table_frame, orient="vertical")
        path_hsb = ttk.Scrollbar(left_table_frame, orient="horizontal")

        self.table_paths = ttk.Treeview(left_table_frame, style="Dark.Treeview",
                                 columns=("Excluded Paths",),
                                 show="headings",
                                 yscrollcommand=path_vsb.set,
                                 xscrollcommand=path_hsb.set)
        
        path_vsb.config(command=self.table_paths.yview)
        path_hsb.config(command=self.table_paths.xview)

        self.table_paths.heading("Excluded Paths", text="Excluded Paths")
        self.table_paths.column("Excluded Paths", width=200, minwidth=200, stretch=True) # stretch=False важливо для горизонтального скролу

        path_vsb.pack(side="right", fill="y")
        path_hsb.pack(side="bottom", fill="x")
        self.table_paths.pack(fill='both', expand=True)
        
        self.populate_table(self.mutedpaths_list, self.table_paths)

        left_contr_frame = ttk.Frame(left_table_frame)
        left_contr_frame.pack(fill='x')

        self.path_to_mute_entry = ttk.Entry(left_contr_frame)
        self.path_to_mute_entry.pack(side='left', fill='x', padx=(0, 5))

        ttk.Button(left_contr_frame, text="Search", command=None).pack(side='left')
        ttk.Button(left_contr_frame, text="+", command=
                   lambda: self.add_record(self.path_to_mute_entry, self.mutedpaths_list, self.table_paths, 'paths')).pack(side='left')
        ttk.Button(left_contr_frame, text="-", command=
                   lambda: self.delete_record(self.table_paths, self.mutedpaths_list)).pack(side='left')


        right_table_frame = ttk.Frame(tables_container)
        right_table_frame.pack(side="left", fill="y", expand=True, padx=(10, 0))

        ext_vsb = ttk.Scrollbar(right_table_frame, orient="vertical")
        ext_hsb = ttk.Scrollbar(right_table_frame, orient="horizontal")

        self.table_exts = ttk.Treeview(right_table_frame, style="Dark.Treeview",
                                 columns=("Excluded Extensions",),
                                 show="headings",
                                 yscrollcommand=ext_vsb.set,
                                 xscrollcommand=ext_hsb.set)
        
        ext_vsb.config(command=self.table_exts.yview)
        ext_hsb.config(command=self.table_exts.xview)

        self.table_exts.heading("Excluded Extensions", text="Excluded Extensions")
        self.table_exts.column("Excluded Extensions", width=150, minwidth=150, stretch=True)

        # Пакуємо
        ext_vsb.pack(side="right", fill="y")
        ext_hsb.pack(side="bottom", fill="x")
        self.table_exts.pack(fill='both', expand=True)
        
        self.populate_table(self.mutedext_list, self.table_exts)

        right_contr_frame = ttk.Frame(right_table_frame)
        right_contr_frame.pack(fill='x')
        self.ext_to_mute_entry = ttk.Entry(right_contr_frame)
        self.ext_to_mute_entry.pack(side='left', fill='x', padx=(0, 5))
        ttk.Button(right_contr_frame, text="+", command=
                   lambda: self.add_record(self.ext_to_mute_entry, self.mutedext_list, self.table_exts, 'extensions')).pack(side='left')
        ttk.Button(right_contr_frame, text="-", command=
                   lambda: self.delete_record(self.table_exts, self.mutedext_list)).pack(side='left')
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(side='top')
        ttk.Button(btn_frame, text="Save", command=self.on_save, style="Red.TButton").pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right")

        self.wait_window()
    
    def on_save(self):
        self.thr_limit_atr = self.thr_limit_entry.get()
        self.mute_duration_atr = self.mute_duration_entry.get()
        try:
            self.thr_limit_atr = int(self.thr_limit_atr)
            self.mute_duration_atr = int(self.mute_duration_atr)
            if self.thr_limit_atr<2 or self.mute_duration_atr<=0:
                messagebox.showerror('Invalid entry', 'Enter valid values and try again')
                return
        except:
            messagebox.showerror('Entry fields are empty', 'Enter values and try again')
            return
        
        with back.CONFIG_LOCK:
            back.THROTTLE_LIMIT = self.thr_limit_atr
            back.MUTE_DURATION = self.mute_duration_atr

            #валідація system_paths
            back.SYSTEM_PATHS = self.mutedpaths_list.copy()

            #валідація system_extensions
            back.SYSTEM_EXTENSIONS = self.mutedext_list.copy()

            settings = {
                'THROTTLE_LIMIT':self.thr_limit_atr,
                'MUTE_DURATION':self.mute_duration_atr,
                'MUTED_PATHS':self.mutedpaths_list,
                'MUTED_EXTENSIONS':self.mutedext_list
            }

            is_success = back.writing_profs(self.logsSettings_path, settings, debug=True)
            back.CONFIG_UPDATE_EVENT.set()

        self.destroy()

    def validate_on_key(self, value):
        if value == '':
            return True
        elif value.isdigit():
            return True
        return False

    def populate_table(self, list_of_str, data_tree):
        """Fill Table with data"""
        data_tree.delete(*data_tree.get_children())
        
        for string in list_of_str:
            
            data_tree.insert("", "end", iid = string, values=(string, ))
    

    def add_record(self, entry_object, target_list, tree_object, record_type):
        string = entry_object.get().strip()
        if string:
            if record_type == 'paths':
                string = os.path.normpath(string)
                if not string.endswith(os.path.sep):
                    string = string + os.path.sep
            elif record_type == 'extensions':
                if not string.startswith('.'):
                    string = '.' + string

            if not string.lower() in target_list:
                target_list.append(string.lower())
                self.populate_table(target_list, tree_object)
                entry_object.delete(0, "end")


    def delete_record(self, tree_object, target_list):
        selection = tree_object.selection()
        #if not selection: 
        #    messagebox.showwarning(f"No selection", "Please select a value to unmute.", parent=self)
        #    return
        for item in selection:
            if item in target_list:
                target_list.remove(item)
        self.populate_table(target_list, tree_object)



class LogsPage(tk.Frame):
    """Loggin Menu"""
    def __init__(self, parent, controller):
        super().__init__(parent, bg=bg_c)
        self.controller = controller
        self.log_data = []

        #   --- First Upper Frame ---
        f_top_frame = ttk.Frame(self, style="TFrame")
        f_top_frame.pack(side="top", fill="x", padx=10, pady=5)

        ttk.Button(f_top_frame, text="Refresh", command=self.load_logs).pack(side="left", padx=2)
        ttk.Button(f_top_frame, text="Delete", command=self._delete_selected_log).pack(side="left", padx=2)
        ttk.Button(f_top_frame, text="Select All", command=self._select_all_logs).pack(side="left", padx=2)
        ttk.Button(f_top_frame, text="Undo", command=self._undo_action).pack(side="left", padx=2)
        ttk.Button(f_top_frame, text="Settings", command=self._add_new_settings).pack(side="left", padx=(20, 10))
        ttk.Button(f_top_frame, text="Return", command=lambda: controller.show_frame("StartPage")).pack(side="right")

        #   --- Second Upper Frame ---
        s_top_frame = ttk.Frame(self, style="TFrame")
        s_top_frame.pack(side="top", fill="x", padx=10, pady=5)

        ttk.Label(s_top_frame, text="Search:").pack(side="left", padx=(10, 2))
        self.search_entry = ttk.Entry(s_top_frame)
        self.search_entry.pack(side="left", padx=2)

        self.status_filter = ttk.Combobox(s_top_frame, values=["All", "Created", "Deleted", "Moved", "Renamed"], state="readonly")
        self.status_filter.set("All")
        self.status_filter.pack(side="left", padx=10)

        self.search_entry.bind("<KeyRelease>", self.filter_logs)
        self.status_filter.bind("<<ComboboxSelected>>", self.filter_logs)

        #   --- Main Part: Table and details ---
        main_content = ttk.Frame(self, style="TFrame")
        main_content.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        #   --- Log Table ---
        log_table_frame = ttk.Frame(main_content)
        log_table_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(log_table_frame, style="Dark.Treeview",
                                 columns=("Num", "Timestamp", "Status", "Source Path", "Destination Path"),
                                 show="headings")
        self.tree.pack(side="left", fill="both", expand=True)
        
        vsb = ttk.Scrollbar(log_table_frame, orient="vertical", command=self.tree.yview)
        vsb.pack(side='right', fill='y')
        self.tree.configure(yscrollcommand=vsb.set)

        #   Columns
        self.tree.heading("Num", text="#")
        self.tree.column("Num", width=50, stretch=False)
        self.tree.heading("Timestamp", text="Timestamp")
        self.tree.column("Timestamp", width=150, stretch=False)
        self.tree.heading("Status", text="Status")
        self.tree.column("Status", width=100, stretch=False)
        self.tree.heading("Source Path", text="Source Path")
        self.tree.column("Source Path", width=250, stretch=True)
        self.tree.heading("Destination Path", text="Destination Path")
        self.tree.column("Destination Path", width=250, stretch=True)

        #   Bind row selection to info show
        self.tree.bind("<<TreeviewSelect>>", self._on_row_select)

        #   --- Lower Panel for details ---
        self.details_frame = ttk.LabelFrame(main_content, text="Issue Details", style="TLabelframe")
        # Hide it for now
        
        self.details_text = tk.Text(self.details_frame, wrap="word", height=6, bg="#3C3F41", fg="white", borderwidth=0)
        self.details_text.pack(fill="both", expand=True, padx=5, pady=5)

    def _periodic_log_check(self):
        """Checks logs periodicaly"""
        try:
            buffer_len = 0
            with back.lock:
                buffer_len = len(back.buffer2)
            if len(self.log_data) != buffer_len:
                self.load_logs()
        except AttributeError:
            pass
        self.after_id = self.after(1000, self._periodic_log_check)

    def on_show(self):
        """Calls when menu is opened"""
        self.load_logs()
        self._periodic_log_check()

    def on_hide(self):
        """Calls when menu is hiden and stops the checks"""
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

    def load_logs(self):
        """Load logs from backend"""
        try:
            self.log_data = back.get_safe_logs()
        except AttributeError:
            self.log_data = []

        self.filter_logs()

    def filter_logs(self, event=None):
        """Filter self.log_data based on status and dropdown menu"""
        search_term = self.search_entry.get().lower()
        status_filter = self.status_filter.get().lower()

        filtered_data = []
        
        for log_entry in self.log_data:
            action_type = log_entry.get("action_type", "")
            status_match = (status_filter == "all" or action_type == status_filter)

            src_path = log_entry.get("src_path", "").lower()
            search_match = (search_term in src_path)

            if status_match and search_match:
                filtered_data.append(log_entry)
        
        self.populate_log_table(filtered_data)

    def populate_log_table(self, data_to_display):
        """Fill Table with data"""
        self.tree.delete(*self.tree.get_children())
        
        for log_entry in reversed(data_to_display):
            action = log_entry.get("action_type", "unknown")
            dest_path = log_entry.get("dest_path", "") 
            
            self.tree.insert("", "end", iid=log_entry['num'],
                             values=(
                                log_entry.get("num", ""),
                                log_entry.get("timestamp", ""),
                                action.capitalize(),
                                log_entry.get("src_path", "N/A"),
                                dest_path,
                                "☐"
                            ), tags=(action,))
    
    def _on_row_select(self, event):
        """Show info on row select"""
        selection = self.tree.selection()
        print(selection)###
        if not selection:
            self.details_frame.pack_forget()
            return
        
        selected_iid = selection[0]
        log_entry = next((log for log in self.log_data if log['num'] == int(selected_iid)), None)

        if log_entry:
            details_content = (
                f"Timestamp: {log_entry.get('timestamp')}\n"
                f"Action: {log_entry.get('action_type')}\n"
                f"Source: {log_entry.get('src_path')}"
            )
            if 'dest_path' in log_entry:
                details_content += f"\nDestination: {log_entry.get('dest_path')}"

            self.details_text.delete("1.0", "end")
            self.details_text.insert("1.0", details_content)
            self.details_frame.pack(side="bottom", fill="x", padx=10, pady=10)
        else:
            self.details_frame.pack_forget()

    def _undo_action(self):
        """Sends undo request to backend"""
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning(f"No selection", "Please select a log entry to undo.", parent=self)
            return

        selected_ids = [int(iid) for iid in selection]
        
        back.undo_action(selected_ids, True)
        self.load_logs()

    def _delete_selected_log(self):
        """Deletes log from table"""
        selection = self.tree.selection()
        if not selection: 
            messagebox.showwarning(f"No selection", "Please select a log entry to delete.", parent=self)
            return

        selected_ids = [int(iid) for iid in selection]

        back.delete_from_buffer(selected_ids, True)
        self.load_logs()
    
    def _select_all_logs(self):
        """Selects all logs"""
        all_items = self.tree.get_children()
        if all_items:
            self.tree.selection_set(all_items)
            print(all_items)

    def _add_new_settings(self):
        settings_window = LogsSettings(self)

        
#region Renaming Menu (Andrii)
class RenamingMenu(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=bg_c)
        self.controller = controller
        self.file_data = []
        self.all_columns = []
        self.source_folder_path = None
        self.first_launch = True
        self.renaming_fields=[]
        self.config_file = get_config_path("renaming_config.json")
        self.renaming_config={}

        # Top panel
        top_panel_2 = tk.Frame(self, bg="#3C3F41")
        top_panel_2.pack(side="top", fill="x", padx=10, pady=10) # Виправив fill=None на fill="x"

        # Folder button
        folder_button = ttk.Button(top_panel_2, text="Folder", command=self.load_folder)
        folder_button.pack(side="left", padx=(0, 20))

        # File type filter
        file_type = tk.Frame(top_panel_2, bg="#3C3F41")
        file_type.pack(side="left", padx=10)
        tk.Label(file_type, text="File type:", fg="white", bg="#3C3F41").pack(side="left", padx=5)
        
        self.file_type_combo = ttk.Combobox(file_type, values=["All"], width=15, state="readonly")
        self.file_type_combo.set("All")
        self.file_type_combo.pack(side="left")
        
        self.file_type_combo.bind("<<ComboboxSelected>>", lambda e: self.populate_file_tree(self.source_folder_path))

        # Profile filter
        profile_frame = tk.Frame(top_panel_2, bg="#3C3F41") 
        profile_frame.pack(side="left", padx=10)
        
        tk.Label(profile_frame, text="Profiles:", fg="white", bg="#3C3F41").pack(side="left", padx=5)
        
        self.profile_combo = ttk.Combobox(profile_frame, width=20, state="readonly")
        self.profile_combo.pack(side="left")
        self.profile_combo.bind('<<ComboboxSelected>>', self.apply_profile_config)
        
        ttk.Button(profile_frame, text="Save", width=5, 
                   command=self.save_current_profile_manually).pack(side="left", padx=(5, 2))

        # Кнопка додавання (+)
        ttk.Button(profile_frame, text="Add", width=6, 
                   command=self.add_new_profile).pack(side="left", padx=(0, 2))
        
        # Кнопка видалення (-)
        ttk.Button(profile_frame, text="Delete", width=7, 
                   command=self.delete_profile).pack(side="left", padx=0)

        # Return button
        return_button = ttk.Button(top_panel_2, text="Return", command=lambda: controller.show_frame("StartPage"))
        return_button.pack(side="right", padx=5)

        # --Main content--
        content_frame = tk.Frame(self, bg=bg_c)
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Left column - File list table
        content_frame.grid_columnconfigure(0, weight=1, uniform='group')
        content_frame.grid_columnconfigure(1, weight=1, uniform='group')
        content_frame.grid_rowconfigure(0, weight=1)

        left_frame = tk.Frame(content_frame, bg=bg_c)
        left_frame.grid(row=0, column=0, sticky='nsnew', padx=(0, 10))

        # --- ЄДИНА ТАБЛИЦЯ Treeview ---
        self.main_cols_ids = ("Name", "File size", "Date")
        
        self.file_tree = ttk.Treeview(left_frame, show='headings', style="Dark.Treeview")
        self.file_tree["columns"] = self.main_cols_ids
        
        self.file_tree.heading("Name", text="Name", anchor="w")
        self.file_tree.heading("File size", text="File size", anchor="w")
        self.file_tree.heading("Date", text="Date", anchor="w")
        
        self.file_tree.column("Name", width=250, stretch=True, anchor="w") 
        self.file_tree.column("File size", width=100, stretch=True, anchor="w")
        self.file_tree.column("Date", width=150, stretch=True, anchor="w")
        
        self.file_tree["displaycolumns"] = self.main_cols_ids

        # --- Скролбари для єдиної таблиці ---
        vsb = ttk.Scrollbar(left_frame, orient="vertical", command=self.file_tree.yview)
        hsb = ttk.Scrollbar(left_frame, orient="horizontal", command=self.file_tree.xview)
        
        self.file_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        self.file_tree.pack(side='left', fill='both', expand=True) # Пакет після скролбарів

        self.all_columns = list(self.main_cols_ids) # Оновлюємо список всіх колонок
        
        # --- Права колонка та інші елементи залишаються без змін ---

        # Right column - Renaming fields configuration
        right_frame = tk.Frame(content_frame, bg=bg_c)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0)) 
        right_frame.grid_rowconfigure(1, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        self.add_field_btn = ttk.Button(right_frame, text="+", width=3, command=lambda: self.create_renaming_field(f"Field {len(self.renaming_fields) + 1}"))
        self.add_field_btn.grid(row=0, column=0, sticky="e", padx=10, pady=(10, 0))


        # Fields creating
        fields_canvas = tk.Canvas(right_frame, bg=bg_c, highlightthickness=0)
        hsb_right = ttk.Scrollbar(right_frame, orient="horizontal", command=fields_canvas.xview)
        vsb_right=ttk.Scrollbar(right_frame, orient="vertical", command=fields_canvas.yview)
        self.fields_container = tk.Frame(fields_canvas, bg=bg_c)

        fields_canvas.create_window((0, 0), window=self.fields_container, anchor="nw")
        fields_canvas.configure(xscrollcommand=hsb_right.set)
        fields_canvas.configure(yscrollcommand=vsb_right.set)

        fields_canvas.grid(row=1, column=0, sticky="nsew") # Canvas на рядок 1
        hsb_right.grid(row=2, column=0, sticky="ew")
        vsb_right.grid(row=1, column=1, sticky="ns")

        # Log Widget
        log_frame = tk.Frame(right_frame, bg=bg_c)
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        right_frame.grid_rowconfigure(3, weight=1) 

        tk.Label(log_frame, text="Renaming Log", font=("Sans Serif", 12, "bold"), 
             fg="white", bg=bg_c).pack(anchor="w", pady=(0, 5))

        self.log_text = tk.Text(log_frame, height=5, wrap="word", bg="#3C3F41", 
                             fg="white", state="disabled", borderwidth=0)
        log_vsb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_vsb.set)

        log_vsb.pack(side='right', fill='y')
        self.log_text.pack(fill='both', expand=True)

        # Start Renaming button at bottom
        start_button = ttk.Button(right_frame, text="Start Renaming", command=self.start_renaming_thread, style="Red.TButton")
        start_button.grid(row=4, column=0, sticky="se", pady=(10, 0), padx=(0, 10))

        self.load_renaming_config()


    def create_renaming_field(self, field_title, 
                              display_text="", 
                              data_type="Text", 
                              format_text="", 
                              separator="_", 
                              if_absent="Skip"):
        """Creating an *editable* field configuration panel"""
        FIELD_WIDTH=200
        field_frame = tk.Frame(self.fields_container, bg="#3C3F41", relief="ridge", borderwidth=1)
        field_frame.pack(side="left", fill="y", pady=5, padx=5)
        
        field_widgets = {}

        header = tk.Frame(field_frame, bg="#3C3F41")
        header.pack(fill="x", padx=10, pady=(10, 5))
        
        tk.Label(header, text=field_title, font=("Sans Serif", 12, "bold"), 
                 fg="white", bg="#3C3F41").pack(side="left")
        
        del_btn = ttk.Button(header, text="X", width=2, 
                             command=lambda f=field_frame: self.delete_renaming_field(f))
        del_btn.pack(side="right")
        
        # --- Display text 
        display_frame = tk.Frame(field_frame, bg="#3C3F41")
        display_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(display_frame, text="Display Text:", font=("Sans Serif", 9), 
                 fg="#999999", bg="#3C3F41").pack(anchor="w")
        display_entry = ttk.Entry(display_frame)
        display_entry.insert(0, display_text)
        display_entry.pack(fill="x")
        field_widgets['display_text'] = display_entry

        # --- Data type 
        data_frame = tk.Frame(field_frame, bg="#3C3F41")
        data_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(data_frame, text="Data Type:", font=("Sans Serif", 9), 
                 fg="#999999", bg="#3C3F41").pack(anchor="w")
        type_combo = ttk.Combobox(data_frame, values=["Text", "Date", "Size", "Metadata Key"], state="readonly")
        type_combo.set(data_type)
        type_combo.pack(fill="x")
        field_widgets['data_type'] = type_combo

        # --- Format 
        format_frame = tk.Frame(field_frame, bg="#3C3F41")
        format_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(format_frame, text="Format (e.g., %Y-%m-%d):", font=("Sans Serif", 9), 
                 fg="#999999", bg="#3C3F41").pack(anchor="w")
        format_entry = ttk.Entry(format_frame)
        format_entry.insert(0, format_text)
        format_entry.pack(fill="x")
        field_widgets['format'] = format_entry

        # --- Separator
        sep_frame = tk.Frame(field_frame, bg="#3C3F41")
        sep_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(sep_frame, text="Separator:", font=("Sans Serif", 9), 
                 fg="#999999", bg="#3C3F41").pack(anchor="w")
        sep_entry = ttk.Entry(sep_frame)
        sep_entry.insert(0, separator)
        sep_entry.pack(fill="x")
        field_widgets['separator'] = sep_entry

        # --- If Absent 
        absent_frame = tk.Frame(field_frame, bg="#3C3F41")
        absent_frame.pack(fill="x", padx=10, pady=(5, 10))
        tk.Label(absent_frame, text="If Absent:", font=("Sans Serif", 9), 
                 fg="#999999", bg="#3C3F41").pack(anchor="w")
        absent_combo = ttk.Combobox(absent_frame, values=["Skip File", "Use Fallback", "Empty String"], state="readonly")
        absent_combo.set(if_absent)
        absent_combo.pack(fill="x")
        field_widgets['if_absent'] = absent_combo

        field_widgets['frame'] = field_frame
        self.renaming_fields.append(field_widgets) 

        self.fields_container.update_idletasks()
        self.fields_container.master.config(scrollregion=self.fields_container.master.bbox("all"))

    def delete_renaming_field(self, frame_to_delete):
            
            field_data = next((item for item in self.renaming_fields if item['frame'] == frame_to_delete), None)
            
            if field_data:
                self.renaming_fields.remove(field_data)
                frame_to_delete.destroy()
                
                self.fields_container.update_idletasks()
                self.fields_container.master.config(scrollregion=self.fields_container.master.bbox("all"))

    def load_folder(self, folder_path=None):
   
        folder = folder_path
        if not folder:
         folder = filedialog.askdirectory(initialdir=open_default_directory)

         if folder:
            self.source_folder_path = folder
            print(f"Folder selected: {folder}") 
            self.populate_file_tree(folder)

    def save_current_profile_manually(self):
        current_profile = self.profile_combo.get()
        
        if not current_profile:
            messagebox.showwarning("Warning", "No profile selected to save.", parent=self)
            return

        if not messagebox.askyesno("Save Profile", f"Overwrite profile '{current_profile}' with current settings?"):
            return

        current_field_data = self.get_fields_data()
        
        if current_profile not in self.renaming_config:
            self.renaming_config[current_profile] = {}

        self.renaming_config[current_profile]["field_config"] = current_field_data
        
        self.renaming_config[current_profile]["source_folder"] = self.source_folder_path
        
        current_ext = self.file_type_combo.get()
        self.renaming_config[current_profile]["file_extensions"] = [current_ext] if current_ext != "All" else []

        self._save_config_to_file()
        
        messagebox.showinfo("Saved", f"Profile '{current_profile}' saved successfully!", parent=self)

    def start_renaming(self):
        """Start the renaming process"""
        if not self.source_folder_path:
            messagebox.showwarning("Warning", "Please select a folder first.", parent=self)
            return
        
        # In actual implementation it will process files here
        print("Starting renaming process...")
        messagebox.showinfo("Renaming", "Renaming process started!", parent=self)

    def on_show(self):
       
        pass


    def populate_file_tree(self, folder):
        if not folder: return
        
        current_selection = self.file_type_combo.get()
        target_ext = current_selection.lower() if current_selection != "All" else None

        self.file_tree.delete(*self.file_tree.get_children())
        
        self.file_tree.tag_configure('separator', background="#454545", foreground="#AAAAAA")

        found_extensions = set()
        display_data = []

        try:
            all_files = os.listdir(folder)
            
            for filename in all_files:
                filepath = os.path.join(folder, filename)
                
                if os.path.isfile(filepath):
                    _, ext = os.path.splitext(filename)
                    ext_lower = ext.lower()

                    if ext: 
                        found_extensions.add(ext_lower)
                    
                    if ext_lower == '.exe' or filename.startswith('.'):
                        continue

                    file_info = {
                        "name": filename,
                        "ext": ext_lower,
                        "size": "N/A",
                        "date": "N/A"
                    }

                    try:
                        file_size = os.path.getsize(filepath)
                        mod_time = os.path.getmtime(filepath)
                        date_str = datetime.datetime.fromtimestamp(mod_time).strftime('%Y-%m-%d %H:%M')
                        
                        file_info["size"] = f"{file_size/1024:.2f}"
                        file_info["date"] = date_str
                    except Exception:
                        pass
                    
                    display_data.append(file_info)

            sorted_exts = sorted(list(found_extensions))
            sorted_exts.insert(0, "All")
            
            self.file_type_combo['values'] = sorted_exts
            
            if current_selection not in sorted_exts:
                self.file_type_combo.set("All")
                target_ext = None
            else:
                self.file_type_combo.set(current_selection)

            if target_ext:
                display_data.sort(key=lambda x: (x['ext'] != target_ext, x['name']))
            else:
                display_data.sort(key=lambda x: x['name'])

            separator_inserted = False

            for item in display_data:
                if target_ext and not separator_inserted and item['ext'] != target_ext:
                    self.file_tree.insert("", "end", 
                                          values=("--- Others ---", "", ""), 
                                          tags=('separator',)) 
                    separator_inserted = True

                self.file_tree.insert("", "end", values=(item["name"], item["size"], item["date"]))
                        
        except Exception as e:
            self.log_message(f"Error reading folder: {e}")   

    def log_message(self, message):
        if not hasattr(self, 'log_text'):
            return
        self.log_text.config(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def start_renaming_thread(self):
        if not self.source_folder_path:
            messagebox.showwarning("Warning", "Please select a folder first.", parent=self)
            return
        
        rules = self.get_fields_data()
        
        if not rules:
             messagebox.showwarning("Warning", "Please add at least one renaming field.", parent=self)
             return

        target_ext = self.file_type_combo.get()

        start_button = None
        right_frame = self.fields_container.master.master 
        for w in right_frame.grid_slaves(row=4, column=0):
            if isinstance(w, ttk.Button):
                start_button = w
                break

        if start_button:
            start_button.config(text="Renaming...", state="disabled")

        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

        ui_log_callback = lambda msg: self.after(0, self.log_message, msg)

        threading.Thread(
            target=self.run_renaming_logic, 
            
            args=(self.source_folder_path, rules, ui_log_callback, start_button, target_ext), 
            daemon=True
        ).start()

    def run_renaming_logic(self, folder, rules, log_callback, start_button, target_ext):
        try:
            if hasattr(back, 'rename_files_from_template'):
                
                back.rename_files_from_template(folder, rules, log_callback, target_extension=target_ext)
            else:
                log_callback("Error: Backend function 'rename_files_from_template' not found!")
            
            self.after(0, self.populate_file_tree, folder)

        except Exception as e:
            log_callback(f"A critical error occurred: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if start_button:
                self.after(0, start_button.config, {"text": "Start Renaming", "state": "normal"})

    def load_renaming_config(self):
        
        try:
            script_dir=os.path.dirname(os.path.abspath(__file__))
            config_path=os.path.join(script_dir, self.config_file)
        
            with open(config_path, 'r', encoding='utf-8') as f:
                self.renaming_config=json.load(f)
                self.log_message(f"Renaming profiles loaded from {self.config_file}")

            profiles = list(self.renaming_config.keys())
            self.profile_combo['values'] = sorted(profiles)

            desired_default = "Camera shots"
            
            if desired_default in profiles:
                self.profile_combo.set(desired_default)
            elif "Custom" in profiles:
                self.profile_combo.set("Custom")
            elif profiles: 
                self.profile_combo.set(profiles[0])

            self.apply_profile_config()

        except FileNotFoundError:
            self.log_message(f"Error: Configuration file '{self.config_file}' not found.")
            
            self.renaming_config = {}
        except json.JSONDecodeError as e:
            self.log_message(f"Error: Invalid JSON format in '{self.config_file}'. Details: {e}")
            self.renaming_config = {}
        except Exception as e:
            self.log_message(f"An unexpected error occurred while loading config: {e}")
            self.renaming_config = {}

    def save_renaming_config(self):
        """Зберігає поточну конфігурацію перейменування у JSON-файл."""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, self.config_file)

            with open(config_path, 'w', encoding='utf-8') as f:
                
                json.dump(self.renaming_config, f, indent=4, ensure_ascii=False)
            
            self.log_message(f"Renaming profiles successfully saved to {self.config_file}")

        except Exception as e:
            self.log_message(f"Error saving renaming config: {e}")

    def add_new_profile(self):
        new_name = simpledialog.askstring("New Profile", "Enter profile name:", parent=self)
        
        if not new_name:
            return
            
        if new_name in self.renaming_config:
            messagebox.showwarning("Duplicate", f"Profile '{new_name}' already exists.", parent=self)
            return

        current_fields = self.get_fields_data()
        current_ext_filter = self.file_type_combo.get()
        ext_list = [current_ext_filter] if current_ext_filter != "All" else []

        self.renaming_config[new_name] = {
            "source_folder": self.source_folder_path,
            "file_extensions": ext_list,
            "field_config": current_fields
        }

        self._save_config_to_file()

        self._refresh_profile_list(select_profile=new_name)
        
        messagebox.showinfo("Success", f"Profile '{new_name}' created!", parent=self)

    def delete_profile(self):
        
        current_profile = self.profile_combo.get()
        
        if not current_profile:
            return

        confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete profile '{current_profile}'?",parent=self)
        if confirm:
            
            if current_profile in self.renaming_config:
                del self.renaming_config[current_profile]
            
            self._save_config_to_file()
            
            self._refresh_profile_list()

    def _save_config_to_file(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, self.config_file)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.renaming_config, f, indent=4, ensure_ascii=False)
            
            self.log_message(f"Config saved to {self.config_file}")
        except Exception as e:
            self.log_message(f"Error saving config file: {e}")
            messagebox.showerror("Error", f"Failed to save config: {e}", parent=self)

    def _refresh_profile_list(self, select_profile=None):
        
        profiles = sorted(list(self.renaming_config.keys()))
        self.profile_combo['values'] = profiles
        
        if select_profile and select_profile in profiles:
            self.profile_combo.set(select_profile)
        elif profiles:
            self.profile_combo.set(profiles[0])
            self.apply_profile_config() 
        else:
            self.profile_combo.set("")

    def parse_and_create_fields(self, naming_template, parameters):
        """
        Розбирає шаблон перейменування та створює відповідні поля в інтерфейсі.
        
        :param naming_template: Шаблон, наприклад, "IMG_DATETIME-ORIGINAL_NAME"
        :param parameters: Словник параметрів.
        """
        
        token_pattern = re.compile(r'([A-Z_]+)') 
        
        matches = list(token_pattern.finditer(naming_template))
        
        # Очищуємо існуючі поля
        for field in self.renaming_fields:
            field['frame'].destroy()
        self.renaming_fields = []
        
        last_end = 0
        field_counter = 1

        for match in matches:
            token_name = match.group(1)
            start, end = match.span()
            
            # 1. СТАТИЧНИЙ ТЕКСТ / РОЗДІЛЬНИК
            static_segment = naming_template[last_end:start]
            if static_segment:
                self.create_renaming_field(
                    field_title=f"Field {field_counter} (Text)",
                    display_text=static_segment,
                    data_type="Text",
                    format_text="",
                    separator="",
                )
                field_counter += 1

            # 2. ДИНАМІЧНИЙ ТОКЕН
            data_type = "Text"
            format_text = ""
            separator = parameters.get('separator', '_') 

            if token_name == "ORIGINAL_NAME":
                data_type = "Original Name"
                separator = "" 
            elif token_name == "DATETIME":
                data_type = "Date"
                format_text = parameters.get(token_name, "{year}{month}{day}_{hour}{minute}")
            elif token_name == "TIMESTAMP":
                data_type = "Timestamp"
                format_text = parameters.get(token_name, "ms")
            else:
                data_type = "Metadata Key"
                format_text = token_name
                
            self.create_renaming_field(
                field_title=f"Field {field_counter} ({data_type})",
                display_text=token_name,
                data_type=data_type,
                format_text=format_text,
                separator=separator
            )
            field_counter += 1
            
            last_end = end 

        # 3. СТАТИЧНИЙ ТЕКСТ (після останнього токена)
        final_static_segment = naming_template[last_end:]
        if final_static_segment:
            self.create_renaming_field(
                field_title=f"Field {field_counter} (Text)",
                display_text=final_static_segment,
                data_type="Text",
                format_text="",
                separator="",
            )

    def apply_profile_config(self, event=None):
        profile_name = self.profile_combo.get()
        if profile_name not in self.renaming_config:
            self.log_message(f"Error: Profile '{profile_name}' not found in config.")
            return

        config = self.renaming_config[profile_name]
        
        # 1. Застосування фільтрів розширень
        file_extensions = config.get("file_extensions", [])
        # Якщо розширення порожні, ми можемо встановити універсальний фільтр або перший елемент зі списку
        if file_extensions:
            # Встановлюємо перше розширення як активний фільтр
            first_ext = f".{file_extensions[0]}" if file_extensions[0] != "*" else file_extensions[0]
            if first_ext in self.file_type_combo['values']:
                self.file_type_combo.set(first_ext)
            
        # 2. Застосування вихідної папки
        source_folder = config.get("source_folder")
        if source_folder and os.path.isdir(source_folder):
            self.source_folder_path = source_folder
            # Оновлюємо таблицю, завантажуючи файли з нової папки
            # self.populate_file_tree(source_folder) # Якщо у вас є метод populate_file_tree
            self.log_message(f"Source folder set to: {source_folder}")
        else:
            self.source_folder_path = None
            self.log_message("Source folder is not set or invalid for this profile.")

        # 3. Оновлення полів перейменування
        
        # Для початку, ви можете просто очистити існуючі поля:
        for field in self.renaming_fields:
            field['frame'].destroy()
        self.renaming_fields = []
        
        field_config = config.get("field_config")

        if field_config:
            # 3.1. Якщо конфігурація полів збережена, відновлюємо її
            for field_data in field_config:
                self.create_renaming_field(
                    field_title=field_data.get("title", "Field"),
                    display_text=field_data.get("display_text", ""),
                    data_type=field_data.get("data_type", "Text"),
                    format_text=field_data.get("format", ""),
                    separator=field_data.get("separator", "_"),
                    if_absent=field_data.get("if_absent", "Skip File")
                )
        else:
            # 3.2. Якщо конфігурації немає (перший запуск), парсимо шаблон
            naming_template = config.get("naming_template", "ORIGINAL_NAME")
            parameters = config.get("parameters", {})
            self.parse_and_create_fields(naming_template, parameters)

        self.log_message(f"Configuration for profile '{profile_name}' applied.")


    def get_fields_data(self):
        collected_data = []
        
        for field_widgets in self.renaming_fields:
            # Збираємо значення з кожного віджета
            data = {
                "display_text": field_widgets['display_text'].get(),
                "data_type": field_widgets['data_type'].get(),
                "format": field_widgets['format'].get(),
                "separator": field_widgets['separator'].get(),
                "if_absent": field_widgets['if_absent'].get()
            }
            collected_data.append(data)

        return collected_data

    def save_renaming_config(self):
        """Зберігає поточну конфігурацію перейменування у JSON-файл."""
        try:
            
            current_profile_name = self.profile_combo.get()
            if not current_profile_name:
                return 

            current_field_data = self.get_fields_data()
            
            if current_profile_name not in self.renaming_config:
                self.renaming_config[current_profile_name] = {}
                
            self.renaming_config[current_profile_name]["field_config"] = current_field_data
            
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, self.config_file)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.renaming_config, f, indent=4, ensure_ascii=False)
            
            print(f"Config saved for profile: {current_profile_name}")

        except Exception as e:
            self.log_message(f"Error saving renaming config: {e}")


#region Desktop

class DesktopPage(tk.Frame):
    """
    Menu for visual creation of zones, 
    which will be used for sorting desktop.
    """
    def __init__(self, parent, controller):
        super().__init__(parent, bg=bg_c)
        self.controller = controller
        self.config_file = get_config_path("desktop_config.json")
        self.max_zones = 10
        self.after_id_autosave = None


        #   For interactive panel
        self.selected_zone = None           #   Name of chosen zone
        self.drag_mode = None               #   "move", "resize_br" (bottom-right) etc.
        self.start_x = 0                    #   Start X position
        self.start_y = 0                    #   Start Y position
        self.resize_handle_size = 10        #   Size of handle to resize in pixels
        self.min_zone_size_percent = 0.2    #   15% from width/heigth of screen
        self.default_zone_width = 0.3       #   30% width
        self.default_zone_height = 0.3      #   30% heigth

        #   --- Data to save ---
        self.zones = {}         #   Zones dictionary
        self.rules = []         #   Rules list
        self.settings = {"check_frequency": "Every 1 min", "enabled": False}

        self.frequency_map = {
            "Every 6 seconds": 0.1,
            "Every 30 seconds": 0.5,
            "Every 1 min": 1,
            "Every 5 mins": 5,
            "Every 15 mins": 15,
            "Every 1 hour": 60,
            "Every 6 hours": 360,
            "Every 12 hours": 720
        }

        #   Get resolution
        # --- ВИПРАВЛЕННЯ МАСШТАБУВАННЯ (REAL DPI FIX) ---
        # 1. Отримуємо те, що "бачить" програма (напр. 1536x864)
        logical_width = self.controller.winfo_screenwidth()
        logical_height = self.controller.winfo_screenheight()
        
        try:
            import ctypes
            # Визначаємо структуру для отримання справжніх налаштувань відеокарти
            class DEVMODE(ctypes.Structure):
                _fields_ = [
                    ("dmDeviceName", ctypes.c_char * 32),
                    ("dmSpecVersion", ctypes.c_ushort),
                    ("dmDriverVersion", ctypes.c_ushort),
                    ("dmSize", ctypes.c_ushort),
                    ("dmDriverExtra", ctypes.c_ushort),
                    ("dmFields", ctypes.c_uint),
                    ("dmOrientation", ctypes.c_short),
                    ("dmPaperSize", ctypes.c_short),
                    ("dmPaperLength", ctypes.c_short),
                    ("dmPaperWidth", ctypes.c_short),
                    ("dmScale", ctypes.c_short),
                    ("dmCopies", ctypes.c_short),
                    ("dmDefaultSource", ctypes.c_short),
                    ("dmPrintQuality", ctypes.c_short),
                    ("dmColor", ctypes.c_short),
                    ("dmDuplex", ctypes.c_short),
                    ("dmYResolution", ctypes.c_short),
                    ("dmTTOption", ctypes.c_short),
                    ("dmCollate", ctypes.c_short),
                    ("dmFormName", ctypes.c_char * 32),
                    ("dmLogPixels", ctypes.c_ushort),
                    ("dmBitsPerPel", ctypes.c_uint),
                    ("dmPelsWidth", ctypes.c_uint),  # <--- Це те, що нам треба (Реальна ширина)
                    ("dmPelsHeight", ctypes.c_uint), # <--- Це те, що нам треба (Реальна висота)
                ]
            
            devmode = DEVMODE()
            devmode.dmSize = ctypes.sizeof(DEVMODE)
            
            # Викликаємо EnumDisplaySettings (отримуємо поточні налаштування головного екрану)
            # -1 означає ENUM_CURRENT_SETTINGS
            ctypes.windll.user32.EnumDisplaySettingsA(None, -1, ctypes.byref(devmode))
            
            self.screen_width = devmode.dmPelsWidth
            self.screen_height = devmode.dmPelsHeight
            
            # Розрахунок масштабу для відладки
            scale = self.screen_width / logical_width
            print(f"DPI Corrected: Logical {logical_width}x{logical_height} -> Real {self.screen_width}x{self.screen_height} (Scale: {scale:.2f})")

        except Exception as e:
            print(f"DPI Detection failed: {e}")
            # Запасний варіант - використовуємо логічні розміри
            self.screen_width = logical_width
            self.screen_height = logical_height

        self.aspect_ratio = self.screen_height / self.screen_width
        # ------------------------------------------------

        #   --- Upper panel ---
        top_panel = ttk.Frame(self, style="TFrame")
        top_panel.pack(side="top", fill="x", padx=10, pady=10)

        ttk.Button(top_panel, text="Return", command=lambda: controller.show_frame("StartPage")).pack(side="right")

        #   --- Main content ---
        main_frame = ttk.Frame(self, style="TFrame")
        main_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        #   --- Left column ---
        left_column = ttk.Frame(main_frame, width=350)
        left_column.pack_propagate(False)
        left_column.pack(side="left", fill="y", padx=(0, 10))

        #   --- Right column ---
        #   Move Canvas into a frame to control the size.
        right_column = ttk.Frame(main_frame, style="TFrame")
        right_column.pack(side="right", fill="both", expand=True)

        self.canvas_frame = ttk.Frame(right_column)
        self.canvas_frame.pack(fill="both", expand=True)

        self.grid_canvas = tk.Canvas(self.canvas_frame, bg="#3C3F41", highlightthickness=0)
        self.grid_canvas.pack()
        self.canvas_frame.bind("<Configure>", self._on_canvas_resize)
        self.grid_canvas.bind("<Button-1>", self._on_canvas_press)
        self.grid_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.grid_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

        canvas_controls = ttk.Frame(right_column, style="TFrame")
        canvas_controls.pack(fill="x", pady=(5, 0))
        ttk.Button(canvas_controls, text="Add New Zone", command=self.add_new_zone).pack(side="left", padx=5)
        ttk.Button(canvas_controls, text="Delete Selected Zone", command=self._delete_selected_zone).pack(side="left", padx=5)
        #   --- Left column content ---
        #   1. Zone redactor
        zone_editor_frame = ttk.LabelFrame(left_column, text="Group menu")
        zone_editor_frame.pack(fill="x", expand=False)
        self.create_zone_editor(zone_editor_frame)

        #   2. Rule redactor
        rules_editor_frame = ttk.LabelFrame(left_column, text="Move to")
        rules_editor_frame.pack(fill="both", expand=True, pady=10)
        self.create_rules_editor(rules_editor_frame)

        #   3. Settings
        settings_frame = ttk.Frame(right_column, style="TFrame")
        settings_frame.pack(fill="x", padx=5, pady=(10, 0))
        self.create_settings_panel(settings_frame)
        
        #   Load config
        #self.load_config()
        pass

    def on_show(self):
        """Called on menu open"""
        self.load_config()

    #   --- Save/Load ---
    def save_config(self):
        """Save config to json"""
        print("Saving configuration...")
        
        zones_to_save = {}
        for name, data in self.zones.items():
            coords_pct = data["coords"]
            coords_px = (
                int(coords_pct[0] * self.screen_width),
                int(coords_pct[1] * self.screen_height),
                int(coords_pct[2] * self.screen_width),
                int(coords_pct[3] * self.screen_height)
            )
            zones_to_save[name] = data.copy()
            zones_to_save[name]["coords"] = coords_px

        frequency_minutes = self.frequency_map.get(self.freq_combo.get(), 1)

        config_data = {
            "desktop_zones": zones_to_save,
            "desktop_rules": self.rules,
            "desktop_settings": {
                "check_frequency": frequency_minutes,
                "enabled": self.settings["enabled"]
            }
        }
        success = writing_profs(config_data, debug=False, path=self.config_file)
        if success:
            print("Config saved.")
        else:
            print(f"Error saving config to {self.config_file}")

    def load_config(self):
        """Load config from json"""
        print("Loading configuration...")
        config_data = back.reading_profs(debug=False, path=self.config_file)
        
        if config_data:
            loaded_zones = config_data.get("desktop_zones", {})
            self.zones = {}
            for name, data in loaded_zones.items():
                coords_px = data.get("coords", (0, 0, 0, 0))
                coords_pct = (
                    coords_px[0] / self.screen_width,
                    coords_px[1] / self.screen_height,
                    coords_px[2] / self.screen_width,
                    coords_px[3] / self.screen_height
                )
                self.zones[name] = data.copy()
                self.zones[name]["coords"] = coords_pct
            
            self.rules = config_data.get("desktop_rules", [])
            self.settings = config_data.get("desktop_settings", self.settings)

            frequency_minutes = self.settings.get("check_frequency", 1)
            reverse_frequency_map = {v: k for k, v in self.frequency_map.items()}
            frequency_text = reverse_frequency_map.get(frequency_minutes, "Every 1 min")
            self.enable_sorting_var.set(self.settings.get("enabled", False))
            self.freq_combo.set(frequency_text)

        else:
            self.settings = {"check_frequency": 1, "enabled": False}
            self.freq_combo.set("Every 1 min")

        self.update_zone_editor_list()
        self._redraw_canvas()
        self._populate_rules_treeview()

    

    #   --- UI functions ---
    def create_zone_editor(self, parent):
        """Creates UI for Zone redation"""
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill="x", expand=True, padx=5, pady=5)
        
        list_scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        self.zone_listbox = tk.Listbox(list_frame, height=5, yscrollcommand=list_scrollbar.set,
                                        bg="#3C3F41", fg="white", selectbackground="#1E5F8A",
                                        exportselection=False)
        list_scrollbar.config(command=self.zone_listbox.yview)
        list_scrollbar.pack(side="right", fill="y")
        self.zone_listbox.pack(side="left", fill="x", expand=True)

        self.zone_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        ttk.Button(parent, text="Add new group +", command=self.add_new_zone).pack(fill="x", padx=5, pady=5)
        
        props_frame = ttk.Frame(parent)
        props_frame.pack(fill="x", padx=5, pady=(5, 10))

        props_frame.grid_columnconfigure(1, weight=1)
        props_frame.grid_columnconfigure(3, weight=1)
        
        ttk.Label(props_frame, text="Name:").grid(row=0, column=0, sticky="w", padx=2)
        self.zone_name_entry = ttk.Entry(props_frame)
        self.zone_name_entry.grid(row=0, column=1, columnspan=3, sticky="ew", pady=2)

        ttk.Label(props_frame, text="X1:").grid(row=1, column=0, sticky="w", padx=2)
        self.zone_x1_entry = ttk.Entry(props_frame, width=8)
        self.zone_x1_entry.grid(row=1, column=1, sticky="w", pady=2)
        
        ttk.Label(props_frame, text="Y1:").grid(row=1, column=2, sticky="w", padx=2)
        self.zone_y1_entry = ttk.Entry(props_frame, width=8)
        self.zone_y1_entry.grid(row=1, column=3, sticky="w", pady=2)

        ttk.Label(props_frame, text="Width:").grid(row=2, column=0, sticky="w", padx=2)
        self.zone_width_entry = ttk.Entry(props_frame, width=8)
        self.zone_width_entry.grid(row=2, column=1, sticky="w", pady=2)
        
        ttk.Label(props_frame, text="Height:").grid(row=2, column=2, sticky="w", padx=2)
        self.zone_height_entry = ttk.Entry(props_frame, width=8)
        self.zone_height_entry.grid(row=2, column=3, sticky="w", pady=2)

        ttk.Button(props_frame, text="Apply Changes", command=self._apply_editor_changes).grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10,0))

    def create_rules_editor(self, parent):
        """Create UI for rules redaction"""
        
        # --- 1. КНОПКИ (ПАКУЄМО ВНИЗ СПОЧАТКУ) ---
        # Ми кажемо кнопкам "приклеїтися" до низу фрейму
        btn_frame = ttk.Frame(parent)
        btn_frame.pack(side="bottom", fill="x", padx=5, pady=5)
        
        ttk.Button(btn_frame, text="+ Add New Rule", command=self._add_rule_from_inputs).pack(side="left", expand=True, fill="x")
        ttk.Button(btn_frame, text="- Delete Selected Rule", command=self._delete_selected_rule).pack(side="left", expand=True, fill="x", padx=(5,0))

        # --- 2. ТАБЛИЦЯ (ЗАПОВНЮЄ ВЕСЬ ЗАЛИШОК) ---
        # Тепер таблиця займе весь простір, що залишився НАД кнопками
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.rules_tree = ttk.Treeview(tree_frame, height=5,
                                       columns=("Criterion", "Operator", "Value", "Destination"),
                                       show="headings", style="Dark.Treeview")
        self.rules_tree.pack(side="left", fill="both", expand=True)
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.rules_tree.yview)
        vsb.pack(side='right', fill='y')
        self.rules_tree.configure(yscrollcommand=vsb.set)

        # Налаштування колонок (залишається без змін)
        self.rules_tree.heading("Criterion", text="Criterion")
        self.rules_tree.column("Criterion", width=80)
        self.rules_tree.heading("Operator", text="Operator")
        self.rules_tree.column("Operator", width=70)
        self.rules_tree.heading("Value", text="Value")
        self.rules_tree.column("Value", width=60)
        self.rules_tree.heading("Destination", text="Destination")
        self.rules_tree.column("Destination", width=100)

        
    def _add_rule_from_inputs(self):
        """Create a dialog to create new window"""
        destinations = list(self.zones.keys())
        criteria = ["Name", "Extension", "Size", "Date Created"]
        
        dialog = RuleEditorDialog(self, 
                                  available_destinations=destinations, 
                                  available_criteria=criteria)
        
        if dialog.result:
            self.rules.append(dialog.result)
            self._populate_rules_treeview()
            self._trigger_auto_save()

    def _delete_selected_rule(self):
        """Delete rule from table"""
        selection = self.rules_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a rule from the list to delete.", parent=self)
            return

        selected_iid = selection[0]
        index = self.rules_tree.index(selected_iid)
        
        self.rules.pop(index)
        
        self._populate_rules_treeview()
        self._trigger_auto_save()

    def _populate_rules_treeview(self):
        """Filling the rule table"""
        self.rules_tree.delete(*self.rules_tree.get_children())
        for rule in self.rules:
            self.rules_tree.insert("", "end", values=(
                rule.get("criterion", ""),
                rule.get("operator", ""),
                rule.get("value", ""),
                rule.get("destination", "")
            ))

    # def _update_rule_destinations_combo(self):
    #     """Update dropdown menu"""
    #     zone_names = list(self.zones.keys())
    #     current_val = self.rule_dest_combo.get()
    #     if current_val and current_val not in zone_names:
    #         zone_names.append(current_val)
            
    #     self.rule_dest_combo['values'] = zone_names

    def _browse_rule_dest(self):
        """Open file dialog"""
        path = filedialog.askdirectory(initialdir=open_default_directory)
        if path:
            self.rule_dest_combo.set(path)

    def create_settings_panel(self, parent):
        """Creates UI for setting pannel"""
        self.enable_sorting_var = tk.BooleanVar(value=self.settings.get("enabled", False))
        cb = ttk.Checkbutton(parent, text="Enable desktop sorting", 
                             variable=self.enable_sorting_var,
                             command=self._on_toggle_sorting)
        cb.pack(anchor="w", padx=5)
        
        ttk.Label(parent, text="Check frequency:").pack(anchor="w", padx=5, pady=(5,0))
        
        self.freq_combo = ttk.Combobox(parent, values=["Every 6 seconds", "Every 30 seconds", "Every 1 min", "Every 5 mins", "Every 15 mins", "Every 1 hour", "Every 6 hours", "Every 12 hours"], state="readonly")
        self.freq_combo.set(self.settings.get("check_frequency", "Every 1 min"))
        self.freq_combo.pack(fill="x", padx=5, pady=5)
        self.freq_combo.bind("<<ComboboxSelected>>", self._on_freq_change)

    def _on_freq_change(self, event=None):
        """Saves only time change"""
        self.settings["check_frequency"] = self.frequency_map.get(self.freq_combo.get(), 1)
        self._trigger_auto_save()
    
    def _on_toggle_sorting(self, event=None):
        """Called uppon toggling desktop sorting"""
        is_enabled = self.enable_sorting_var.get()
        if is_enabled:
            confirm = messagebox.askyesno(
                title="Enable Desktop Sorting?",
                message="Warning: This feature will actively monitor and move files on your desktop based on your rules.\n\nFor correct work your desktop should not use grid or autosort functions.\n\nAre you sure you want to enable it?",
                parent=self
            )
            if confirm:
                self.settings["enabled"] = True
                print("Desktop sorting ENABLED.")
            else:
                self.enable_sorting_var.set(False)
        else:
            self.settings["enabled"] = False
            print("Desktop sorting DISABLED.")
        
        self._trigger_auto_save()

    def _rename_zone_in_rules(self, old_name: str, new_name: str):
        """Update zone name in rules"""
        changed = False
        for rule in self.rules:
            if rule.get("destination") == old_name:
                rule["destination"] = new_name
                changed = True
        if changed:
            self._populate_rules_treeview()
            self._trigger_auto_save()

    def _trigger_auto_save(self):
        """Start autosave data"""
        #   Cancel planned save
        if self.after_id_autosave:
            self.after_cancel(self.after_id_autosave)
        
        #   Plan save after 1.5 secs
        self.after_id_autosave = self.after(1500, self._validate_and_save)

    def _validate_and_save(self):
        """Check config for errors and saves config"""
        print("Validating config...")
        for zone_name in self.zones:
            if self._check_overlap(zone_name, self.zones[zone_name]["coords"]):
                messagebox.showerror("Save Error", f"Cannot save: Zone '{zone_name}' is overlapping with another zone.", parent=self)
                return
        
        self.save_config()

    #   --- Zone and Canvas Logic ---
    def add_new_zone(self):
        """Create new zone."""
        if len(self.zones) >= self.max_zones:
            messagebox.showwarning("Limit Reached", f"You cannot create more than {self.max_zones} zones.")
            return

        #   Create unique name
        new_name = f"Group {len(self.zones) + 1}"
        i = 1
        while new_name in self.zones:
            i += 1
            new_name = f"Group {i}"
        

        new_coords = self._find_empty_spot(self.default_zone_width, self.default_zone_height)
        if new_coords is None:
            messagebox.showwarning("No Space", "There is not enough free space to add a new zone.", parent=self)
            return

        #   Create new zone with default data.
        self.zones[new_name] = {
            "name": new_name,
            "color": f"#{random.randint(0, 0xFFFFFF):06x}",
            "coords": new_coords,
            "spacing": 100
        }
        
        self.update_zone_editor_list()
        self._redraw_canvas()
        self._trigger_auto_save()
        #self._update_rule_destinations_combo()

    def update_zone_editor_list(self):
        """Updates zone list in zone pannel"""
        self.zone_listbox.delete(0, "end")
        for zone_name in self.zones:
            self.zone_listbox.insert("end", zone_name)

    def _on_canvas_resize(self, event):
        """Resize canvas to match the screen"""
        try:
            if not self.grid_canvas.winfo_exists():
                return

            new_width = event.width
            new_height = int(new_width * self.aspect_ratio)

            self.grid_canvas.config(width=new_width, height=new_height)

            self._redraw_canvas()
            
        except (tk.TclError, Exception):
            pass
    def _redraw_canvas(self):
        """Redraw Zones in canvas"""
        self.grid_canvas.delete("all")
        
        #   Get canvas size
        w = self.grid_canvas.winfo_width()
        h = self.grid_canvas.winfo_height()
        
        if not self.zones:
            if w > 1 and h > 1:
                self.grid_canvas.create_text(w/2, h/2, text="Add a new zone to begin", fill="white", font=("Sans Serif", 12))
            return

        #   Draw each zone
        for zone_name, zone_data in self.zones.items():
            color = zone_data.get("color", "#CCCCCC")
            coords_percent = zone_data.get("coords", (0,0,0,0))
            
            #   Convert % to real pixels
            x1 = coords_percent[0] * w
            y1 = coords_percent[1] * h
            x2 = coords_percent[2] * w
            y2 = coords_percent[3] * h
            
            outline_color = "white" if zone_name == self.selected_zone else ""
            outline_width = 2 if zone_name == self.selected_zone else 0
            
            self.grid_canvas.create_rectangle(x1, y1, x2, y2, 
                                              fill=color, 
                                              outline=outline_color, 
                                              width=outline_width,
                                              tags=(zone_name, "zone"))     #   Adding tags
            
            self.grid_canvas.create_text((x1+x2)/2, (y1+y2)/2, text=zone_name, 
                                         fill="white", 
                                         tags=(zone_name, "text"))
            
            #   Create a handle if the zone is chosen
            if zone_name == self.selected_zone:
                self.grid_canvas.create_rectangle(x2 - self.resize_handle_size, 
                                                  y2 - self.resize_handle_size, 
                                                  x2, y2, 
                                                  fill="white", 
                                                  tags=(zone_name, "resize_handle"))
                
    def _get_zone_at(self, x, y):
        """Return name of zone under cursor"""
        ids = self.grid_canvas.find_closest(x, y)
        if not ids:
            return None
        
        #   Get tags of chosen object
        tags = self.grid_canvas.gettags(ids[0])
        if "zone" in tags:
            return tags[0]          #   First tag - always zone name
        if "resize_handle" in tags:
            return tags[0]          #   Same for handle
        return None

    def _on_canvas_press(self, event):
        """Proccess mouse click on canvas"""
        self.start_x = event.x
        self.start_y = event.y
        
        zone_name = self._get_zone_at(event.x, event.y)
        if zone_name != self.selected_zone:
            self.selected_zone = zone_name
            self._sync_listbox_selection()
            
            if zone_name:
                self._load_zone_data_to_editor(zone_name)
            else:
                self._clear_editor_fields()
        
        self.drag_mode = None
        
        if zone_name:        
            w = self.grid_canvas.winfo_width()
            h = self.grid_canvas.winfo_height()
            coords = self.zones[zone_name]["coords"]
            x2_px = coords[2] * w
            y2_px = coords[3] * h
            
            if (x2_px - self.resize_handle_size < event.x < x2_px) and \
               (y2_px - self.resize_handle_size < event.y < y2_px):
                self.drag_mode = "resize_br"
            else:
                self.drag_mode = "move"
        
        self._redraw_canvas()

    def _on_canvas_drag(self, event):
        """Proccess mouse drag with axis-independent sliding logic"""
        if not self.selected_zone or not self.drag_mode:
            return

        w = self.grid_canvas.winfo_width()
        h = self.grid_canvas.winfo_height()
        if w == 0 or h == 0: return

        #   Get zone coords
        current_coords = self.zones[self.selected_zone]["coords"]
        
        #   Create a copy that will try to change
        final_coords = list(current_coords)     # [x1, y1, x2, y2]
        
        x_move_valid = False
        y_move_valid = False

        #   Calculate wanted change
        dx_percent = (event.x - self.start_x) / w
        dy_percent = (event.y - self.start_y) / h

        if self.drag_mode == "move":
            x1, y1, x2, y2 = current_coords
            width = x2 - x1
            height = y2 - y1

            #   --- 1. X Axis check ---
            new_x1 = max(0.0, min(x1 + dx_percent, 1.0 - width))
            new_x2 = new_x1 + width
            potential_coords_x = (new_x1, y1, new_x2, y2) # Рухаємось по X, стара Y
            
            if not self._check_overlap(self.selected_zone, potential_coords_x):
                final_coords[0] = new_x1
                final_coords[2] = new_x2
                x_move_valid = True

            #   --- 2. Y Axis Check ---
            new_y1 = max(0.0, min(y1 + dy_percent, 1.0 - height))
            new_y2 = new_y1 + height
            potential_coords_y = (final_coords[0], new_y1, final_coords[2], new_y2) 
            
            if not self._check_overlap(self.selected_zone, potential_coords_y):
                final_coords[1] = new_y1
                final_coords[3] = new_y2
                y_move_valid = True
        
        elif self.drag_mode == "resize_br":
            x1, y1, x2, y2 = current_coords
            
            #   --- 1. X Axis Check ---
            new_x2 = min(1.0, x2 + dx_percent)
            if new_x2 < x1 + self.min_zone_size_percent: new_x2 = x1 + self.min_zone_size_percent
            potential_coords_x = (x1, y1, new_x2, y2) # Нова X2, стара Y2
            
            if not self._check_overlap(self.selected_zone, potential_coords_x):
                final_coords[2] = new_x2
                x_move_valid = True

            # --- 2. Y Axis Check ---
            new_y2 = min(1.0, y2 + dy_percent)
            if new_y2 < y1 + self.min_zone_size_percent: new_y2 = y1 + self.min_zone_size_percent
            potential_coords_y = (final_coords[0], final_coords[1], final_coords[2], new_y2)

            if not self._check_overlap(self.selected_zone, potential_coords_y):
                final_coords[3] = new_y2
                y_move_valid = True

        self.zones[self.selected_zone]["coords"] = tuple(final_coords)
        
        if x_move_valid:
            self.start_x = event.x
        if y_move_valid:
            self.start_y = event.y
        
        # Перемальовуємо канвас з новою позицією
        self._redraw_canvas()

    def _on_canvas_release(self, event):
        """Proccess mouse release"""
        if self.drag_mode:
            if self.selected_zone:
                self._load_zone_data_to_editor(self.selected_zone)
            self._trigger_auto_save()
        self.drag_mode = None

    def _check_overlap(self, check_zone_name, potential_coords_percent):
        """Check zone for overlap"""
        w = self.grid_canvas.winfo_width()
        h = self.grid_canvas.winfo_height()
        if w < 2 or h < 2: return False

        c1 = potential_coords_percent
        zone_a = (c1[0]*w, c1[1]*h, c1[2]*w, c1[3]*h)

        for zone_name, zone_data in self.zones.items():
            if zone_name == check_zone_name:
                continue
            
            c2 = zone_data["coords"]
            zone_b = (c2[0]*w, c2[1]*h, c2[2]*w, c2[3]*h)

            # Перевірка AABB
            if (zone_a[2] <= zone_b[0] or    # A left to B
                zone_a[0] >= zone_b[2] or    # A right to B
                zone_a[3] <= zone_b[1] or    # A Up to B
                zone_a[1] >= zone_b[3]):     # A Under B
                continue
            else:
                return True
                
        return False
    
    def _find_empty_spot(self, zone_width, zone_height):
        """Find empty space for creating new zone"""
        step = 0.05     #   Grid step
        
        #   Move on grid from left to right, up to down
        for y_percent in [i * step for i in range(int(1 / step))]:
            for x_percent in [i * step for i in range(int(1 / step))]:
                
                #   Check for out of bounds
                if x_percent + zone_width > 1.01 or y_percent + zone_height > 1.01:
                    continue

                #   Potential cords
                potential_coords = (x_percent, y_percent, x_percent + zone_width, y_percent + zone_height)
                
                #   Create temporary name for check
                temp_check_name = "__temp_check__" 
                
                #   Check for overlap
                if not self._check_overlap(temp_check_name, potential_coords):
                    return potential_coords
        
        #   Didn`t find enough space
        return None
    
    def _on_listbox_select(self, event=None):
        """This function is called upon selecting zone in listbox"""
        selection = self.zone_listbox.curselection()
        if not selection:
            return
            
        zone_name = self.zone_listbox.get(selection[0])
        
        if zone_name != self.selected_zone:
            self.selected_zone = zone_name
            self._load_zone_data_to_editor(zone_name)
            self._redraw_canvas()

    def _sync_listbox_selection(self):
        """Update selection in listbox according to zone selected right now"""
        self.zone_listbox.selection_clear(0, "end")
        if self.selected_zone:
            try:
                all_items = self.zone_listbox.get(0, "end")
                idx = all_items.index(self.selected_zone)
                self.zone_listbox.selection_set(idx)
                self.zone_listbox.activate(idx)
            except ValueError:
                pass
        
    def _clear_editor_fields(self):
        """Clear editor field"""
        self.zone_name_entry.delete(0, "end")
        self.zone_x1_entry.delete(0, "end")
        self.zone_y1_entry.delete(0, "end")
        self.zone_width_entry.delete(0, "end")
        self.zone_height_entry.delete(0, "end")

    def _load_zone_data_to_editor(self, zone_name):
        """Load Editor field"""
        self._clear_editor_fields()
        
        try:
            zone_data = self.zones[zone_name]
            coords = zone_data["coords"]
            
            # Convert (x1,y1,x2,y2) -> (x1,y1,w,h)
            x1_pct = f"{(coords[0] * 100):.2f}"
            y1_pct = f"{(coords[1] * 100):.2f}"
            width_pct = f"{((coords[2] - coords[0]) * 100):.2f}"
            height_pct = f"{((coords[3] - coords[1]) * 100):.2f}"
            
            self.zone_name_entry.insert(0, zone_name)
            self.zone_x1_entry.insert(0, x1_pct)
            self.zone_y1_entry.insert(0, y1_pct)
            self.zone_width_entry.insert(0, width_pct)
            self.zone_height_entry.insert(0, height_pct)
            
        except KeyError:
            messagebox.showerror("Error", f"Could not find data for zone '{zone_name}'.", parent=self)
        except Exception as e:
            print(f"Error loading zone data: {e}")
            
    def _apply_editor_changes(self):
        """Save changes from editor to zones"""
        if not self.selected_zone:
            messagebox.showwarning("No Zone Selected", "Please select a zone to apply changes.", parent=self)
            return

        try:
            #   1. Get data from fields
            new_name = self.zone_name_entry.get().strip()
            x1 = float(self.zone_x1_entry.get()) / 100.0
            y1 = float(self.zone_y1_entry.get()) / 100.0
            width = float(self.zone_width_entry.get()) / 100.0
            height = float(self.zone_height_entry.get()) / 100.0
            
            if not new_name:
                raise ValueError("Name cannot be empty.")
            if width <= 0 or height <= 0:
                raise ValueError("Width and Height must be positive.")

            #   2. Recalculate coords
            x2 = x1 + width
            y2 = y1 + height
            potential_coords = (x1, y1, x2, y2)

            #   3. Validate
            if self._check_overlap(self.selected_zone, potential_coords):
                raise ValueError("New position overlaps with another zone.")
            
            old_name = self.selected_zone
            if new_name != old_name:
                if new_name in self.zones:
                    raise ValueError(f"Zone name '{new_name}' already exists.")
                self._rename_zone_in_rules(old_name, new_name)

            #   4. Update data
            zone_data = self.zones.pop(self.selected_zone)
            
            zone_data["name"] = new_name
            zone_data["coords"] = potential_coords
            
            self.zones[new_name] = zone_data
            self.selected_zone = new_name

            self.update_zone_editor_list()
            self._sync_listbox_selection()
            self._redraw_canvas()
            self._trigger_auto_save()
            #self._update_rule_destinations_combo()
            
        except ValueError as e:
            messagebox.showerror("Invalid Input", f"Could not apply changes: {e}", parent=self)

    def _delete_selected_zone(self):
        """Delete selected zone"""
        if not self.selected_zone:
            messagebox.showwarning("No Zone Selected", "Please select a zone to delete.", parent=self)
            return
        
        used_in_rules = any(r.get("destination") == self.selected_zone for r in self.rules)

        if used_in_rules:
            resp = messagebox.askyesno(
                "Zone used in rules",
                f"Zone '{self.selected_zone}' is referenced in one or more rules.\n"
                "Delete the zone and **remove** all such rules?",
                parent=self)
            if not resp:
                return
            self.rules = [r for r in self.rules if r.get("destination") != self.selected_zone]
            self._populate_rules_treeview()
            
        confirm = messagebox.askyesno(
            "Confirm Delete", 
            f"Are you sure you want to delete '{self.selected_zone}'?",
            parent=self
        )
        
        if confirm:
            del self.zones[self.selected_zone]
            self.selected_zone = None
            
            self._clear_editor_fields()
            self.update_zone_editor_list()
            self._redraw_canvas()
            self._trigger_auto_save()
            #self._update_rule_destinations_combo()

#region Automatization

# У файлі main.py

class RenameTemplateDialog(tk.Toplevel):
    
    def __init__(self, parent, initial_data=None):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Rename Template Editor")
        self.configure(bg=bg_c)

        self.result = None
        self.fields = []        
        
        main_frame = ttk.Frame(self, style="TFrame")
        main_frame.pack(fill="both", expand=True)
        
        canvas = tk.Canvas(main_frame, bg=bg_c, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="horizontal", command=canvas.xview)
        self.fields_container = ttk.Frame(canvas, style="TFrame")

        canvas.create_window((0, 0), window=self.fields_container, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set)
        
        canvas.pack(side="top", fill="both", expand=True)
        scrollbar.pack(side="bottom", fill="x")
        
        self.fields_container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        btn_frame = ttk.Frame(self, style="TFrame")
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Button(btn_frame, text="Add Field +", command=self._add_field).pack(side="left")
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(btn_frame, text="Done", command=self._on_save, style="Red.TButton").pack(side="right", padx=5)

        if initial_data and isinstance(initial_data, list):
            for field_data in initial_data:
                self._add_field(field_data)
        else:
            self._add_field()              
            
        self.wait_window()

    def _add_field(self, data=None):
        if data is None:
            data = {
                "data_type": "Date", 
                "display_text": "",
                "format": "%Y-%m-%d", 
                "separator": "_", 
                "if_absent": "Skip File"
            }

        d_type = data.get("data_type") or data.get("data", "Date")
        
        col = len(self.fields)
        frame = ttk.Frame(self.fields_container, style="TFrame", padding=5, relief="groove", borderwidth=1)
        frame.grid(row=0, column=col, sticky="ns", padx=5, pady=5)
        
        ttk.Label(frame, text=f"Field {col+1}", font=("Arial", 10, "bold")).grid(row=0, column=0, columnspan=2, pady=(0,5))
        
        ttk.Label(frame, text="Type:").grid(row=1, column=0, sticky="w")
        type_combo = ttk.Combobox(frame, values=["Text", "Original Name", "Date", "Size", "Metadata Key"], state="readonly", width=14)
        type_combo.set(d_type)
        type_combo.grid(row=1, column=1)

        ttk.Label(frame, text="Text:").grid(row=2, column=0, sticky="w")
        text_entry = ttk.Entry(frame, width=16)
        text_entry.insert(0, data.get("display_text", ""))
        text_entry.grid(row=2, column=1)

        ttk.Label(frame, text="Format/Key:").grid(row=3, column=0, sticky="w")
        format_entry = ttk.Entry(frame, width=16)
        format_entry.insert(0, data.get("format", ""))
        format_entry.grid(row=3, column=1)

        ttk.Label(frame, text="Separator:").grid(row=4, column=0, sticky="w")
        sep_entry = ttk.Entry(frame, width=16)
        sep_entry.insert(0, data.get("separator", "_"))
        sep_entry.grid(row=4, column=1)

        ttk.Label(frame, text="If Absent:").grid(row=5, column=0, sticky="w")
        absent_combo = ttk.Combobox(frame, values=["Skip File", "Use Fallback", "Empty String"], state="readonly", width=14)
        absent_combo.set(data.get("if_absent", "Skip File"))
        absent_combo.grid(row=5, column=1)
        
        del_btn = ttk.Button(frame, text="Remove", command=lambda f=frame: self._remove_field(f))
        del_btn.grid(row=6, column=0, columnspan=2, pady=(5,0))

        self.fields.append({
            "frame": frame,
            "type": type_combo,
            "text": text_entry,
            "format": format_entry,
            "sep": sep_entry,
            "absent": absent_combo
        })

    def _remove_field(self, frame):
        frame.destroy()
        self.fields = [f for f in self.fields if f["frame"] != frame]
        for i, field in enumerate(self.fields):
            field["frame"].grid(row=0, column=i)

    def _on_save(self):
        self.result = []
        for field in self.fields:
            self.result.append({
                "data_type": field["type"].get(),
                "display_text": field["text"].get(),
                "format": field["format"].get(),
                "separator": field["sep"].get(),
                "if_absent": field["absent"].get()
            })
        self.destroy()

class RuleEditorRow(ttk.Frame):
    """Single row for editing rules"""
    def __init__(self, parent, rule_data, save_callback, master_page):
        super().__init__(parent, style="TFrame", padding=(0, 2))
        self.rule_data = rule_data              #   Link to the main dict
        self.save_callback = save_callback
        self.master_page = master_page
        
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(4, weight=1)
        
        #   --- Create vidgets ---
        self.crit_combo = ttk.Combobox(self, state="readonly", width=10,
                                       values=["Extension", "Name", "Size (MB)", "Created (Days)"])
        self.op_combo = ttk.Combobox(self, state="readonly", width=10,
                                     values=["equals", "contains", "greater than", "less than"])
        self.val_entry = ttk.Entry(self, width=10)
        self.act_combo = ttk.Combobox(self, state="readonly", width=10,
                                      values=["Move", "Rename", "Delete"])
        
        self.details_frame = ttk.Frame(self, style="TFrame")
        
        self.del_btn = ttk.Button(self, text="Delete", command=self._delete_self)

        #   --- Placing everything ---
        self.crit_combo.grid(row=0, column=0, padx=(0, 5))
        self.op_combo.grid(row=0, column=1, padx=5)
        self.val_entry.grid(row=0, column=2, padx=5, sticky="ew")
        self.act_combo.grid(row=0, column=3, padx=5)
        self.details_frame.grid(row=0, column=4, padx=5, sticky="ew")
        self.del_btn.grid(row=0, column=5, padx=5)
        
        #   --- Fill in the data ---
        self.crit_combo.set(rule_data.get("criteria", "Extension"))
        self.op_combo.set(rule_data.get("Operation", "equals"))
        self.val_entry.insert(0, rule_data.get("Value", ""))
        self.act_combo.set(rule_data.get("Action", "Move"))
        
        #   --- Linking ---
        self.crit_combo.bind("<<ComboboxSelected>>", self._on_change)
        self.op_combo.bind("<<ComboboxSelected>>", self._on_change)
        self.val_entry.bind("<KeyRelease>", self._on_change)
        self.act_combo.bind("<<ComboboxSelected>>", self._on_action_change)

        self._update_details_widget() # Створюємо правильний віджет "Details"

    def _on_change(self, event=None):
        """Save changes in dictionary"""
        self.rule_data["criteria"] = self.crit_combo.get()
        self.rule_data["Operation"] = self.op_combo.get()
        self.rule_data["Value"] = self.val_entry.get()
        self.rule_data["Action"] = self.act_combo.get()
        
        self.save_callback()

    def _on_action_change(self, event=None):
        """Updates Details field"""
        
        new_action = self.act_combo.get()
        if new_action == "Move":
            if not isinstance(self.rule_data.get("Details"), str):
                self.rule_data["Details"] = ""
        elif new_action == "Rename":
            if not isinstance(self.rule_data.get("Details"), list):
                self.rule_data["Details"] = None
        elif new_action == "Delete":
            self.rule_data["Details"] = None

        self._update_details_widget()
        self._on_change()

    def _update_details_widget(self):
        for widget in self.details_frame.winfo_children():
            widget.destroy()

        try:
            self.details_frame.grid_columnconfigure(0, weight=0)
            self.details_frame.grid_columnconfigure(1, weight=0)
        except tk.TclError:
            pass 

        action = self.act_combo.get()
        
        if action == "Move":
            self.details_frame.grid_columnconfigure(0, weight=0)
            self.details_frame.grid_columnconfigure(1, weight=1)

            details = self.rule_data.get("Details", "")
            if not isinstance(details, str): details = ""

            entry = ttk.Entry(self.details_frame)
            entry.insert(0, details)
            entry.grid(row=0, column=0, sticky="ew") 
            
            btn = ttk.Button(self.details_frame, text="...", width=2, 
                             command=lambda e=entry: self._browse_move(e))
            btn.grid(row=0, column=1, padx=(2,0))
            
        elif action == "Rename":
            self.details_frame.grid_columnconfigure(0, weight=1)
            self.details_frame.grid_columnconfigure(1, weight=0)

            btn = ttk.Button(self.details_frame, text="Template...", 
                             command=self._open_template_dialog)
            btn.grid(row=0, column=0, sticky="ew")
            
        elif action == "Delete":
            pass

    def _browse_move(self, entry_widget):
        path = filedialog.askdirectory(initialdir=open_default_directory)
        if path:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, path)
            self.rule_data["Details"] = path
            self.save_callback()
    
    def _open_template_dialog(self):
        initial_data = self.rule_data.get("Details")
        dialog = RenameTemplateDialog(self, initial_data=initial_data)
        
        if dialog.result:
            self.rule_data["Details"] = dialog.result
            self.save_callback()

    def _delete_self(self):
        """Delete row"""
        self.master_page.delete_rule_row(self)

class AutomationPage(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=bg_c)
        self.controller = controller
        self.config_file = get_config_path("automation_config.json")
        self.automation_config = []
        self.selected_folder = None
        self.after_id_autosave = None

        self.frequency_map = {
            "Every 15 seconds": 0.25,
            "Every 10 mins": 10,
            "Every 30 mins": 30,
            "Every 1 hour": 60,
            "Every 3 hours": 180,
            "Every 6 hours": 360,
            "Every 12 hours": 720,
            "Every 1 day": 1440
        }

        #   --- Top pannel ---
        top_panel = ttk.Frame(self, style="TFrame")
        top_panel.pack(side="top", fill="x", padx=10, pady=10)
        ttk.Button(top_panel, text="Return", command=lambda: controller.show_frame("StartPage")).pack(side="right")

        #   --- Main content ---
        main_frame = ttk.Frame(self, style="TFrame")
        main_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=3)

        #   --- Left column ---
        left_column = ttk.Frame(main_frame)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_column.grid_rowconfigure(1, weight=1)
        left_column.grid_columnconfigure(0, weight=1)

        ttk.Label(left_column, text="Search:").pack(fill="x", padx=5)
        self.folder_search = ttk.Entry(left_column)
        self.folder_search.bind("<KeyRelease>", self._filter_folder_list)   
        self.folder_search.pack(fill="x", padx=5, pady=(0, 5))
        
        folder_tree_frame = ttk.Frame(left_column, width=300)
        folder_tree_frame.pack_propagate(False) 
        folder_tree_frame.pack(fill="both", expand=True)
        
        folder_vsb = ttk.Scrollbar(folder_tree_frame, orient="vertical")
        folder_hsb = ttk.Scrollbar(folder_tree_frame, orient="horizontal")

        # show="tree headings" покаже і структуру папок, і заголовок "Path"
        self.folder_tree = ttk.Treeview(folder_tree_frame, show="tree headings", 
                                        columns=("path",), style="Dark.Treeview",
                                        yscrollcommand=folder_vsb.set, xscrollcommand=folder_hsb.set)
        
        folder_vsb.config(command=self.folder_tree.yview)
        folder_hsb.config(command=self.folder_tree.xview)

        # Колонка #0 (дерево/папки)
        self.folder_tree.heading("#0", text="Folders")
        self.folder_tree.column("#0", width=150, minwidth=100, stretch=False) 
        
        # Колонка Path
        # width=800 (велика ширина для довгих шляхів)
        # stretch=False (не стискатися, щоб працював скрол)
        self.folder_tree.heading("path", text="Path")
        self.folder_tree.column("path", width=800, minwidth=200, stretch=False)

        # Пакуємо
        folder_vsb.pack(side="right", fill="y")
        folder_hsb.pack(side="bottom", fill="x")
        self.folder_tree.pack(side="left", fill="both", expand=True)
        
        self.folder_tree.bind("<<TreeviewSelect>>", self._on_folder_select)

        folder_btn_frame = ttk.Frame(left_column, style="TFrame")
        folder_btn_frame.pack(fill="x", padx=5, pady=5)
        ttk.Button(folder_btn_frame, text="Add new folder +", command=self._add_folder).pack(side="left", expand=True, fill="x")
        ttk.Button(folder_btn_frame, text="Delete folder", command=self._delete_folder).pack(side="left", expand=True, fill="x", padx=(5,0))

        #   --- Right column ---
        right_column = ttk.Frame(main_frame, style="TFrame")
        right_column.grid(row=0, column=1, sticky="nsew")
        right_column.grid_rowconfigure(1, weight=1)
        right_column.grid_columnconfigure(0, weight=1)

        self.rules_title = ttk.Label(right_column, text="AUTOMATION RULES FOR:", font=("Sans Serif", 12, "bold"))
        self.rules_title.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        #   Canvas and scrollbar
        rules_canvas_frame = ttk.Frame(right_column, style="TFrame")
        rules_canvas_frame.grid(row=1, column=0, sticky="nsew", columnspan=2)
        rules_canvas_frame.grid_rowconfigure(0, weight=1)
        rules_canvas_frame.grid_columnconfigure(0, weight=1)

        self.rules_canvas = tk.Canvas(rules_canvas_frame, bg=bg_c, highlightthickness=0)
        rules_sb = ttk.Scrollbar(rules_canvas_frame, orient="vertical", command=self.rules_canvas.yview)
        self.rules_container = ttk.Frame(self.rules_canvas, style="TFrame")

        self.rules_canvas.create_window((0, 0), window=self.rules_container, anchor="nw")
        self.rules_canvas.configure(yscrollcommand=rules_sb.set)
        
        self.rules_canvas.pack(side="left", fill="both", expand=True)
        rules_sb.pack(side="right", fill="y")
        
        self.rules_container.bind("<Configure>", lambda e: self.rules_canvas.configure(scrollregion=self.rules_canvas.bbox("all")))

        ttk.Button(right_column, text="+ Add new rule", command=self._add_new_rule).grid(row=2, column=0, sticky="w", padx=5, pady=5)

        #   Settings at bottom
        settings_frame = ttk.Frame(right_column, style="TFrame")
        settings_frame.grid(row=1, column=0, sticky="es", columnspan=2, padx=5)

        self.setting_enabled_var = tk.BooleanVar()
        self.setting_enabled_toggle = ttk.Checkbutton(settings_frame, text="Automation Enabled",
                                                      variable=self.setting_enabled_var, command=self._on_settings_change)
        self.setting_enabled_toggle.pack(side="right", padx=5)
        
        self.setting_freq_combo = ttk.Combobox(settings_frame, state="readonly", width=15,
                                               values=["Every 15 seconds","Every 10 mins", "Every 30 mins", "Every 1 hour", "Every 3 hours", "Every 6 hours", "Every 12 hours", "Every 1 day"])
        self.setting_freq_combo.pack(side="right")
        ttk.Label(settings_frame, text="Check frequency:").pack(side="right", padx=(5,2))
        self.setting_freq_combo.bind("<<ComboboxSelected>>", self._on_settings_change)

        
        
    def on_show(self):
        self.load_config()

    def load_config(self):
        self.automation_config = back.reading_profs(debug=False, path=self.config_file)
        if not isinstance(self.automation_config, list):
            self.automation_config = []
        self._populate_folder_list()
        self._populate_rules_list(None)
        self._update_settings_ui(None)

    def save_config(self):
        back.writing_profs(self.config_file, self.automation_config, debug=False)
        print("Automation config saved.")
        
    def _trigger_auto_save(self):
        if self.after_id_autosave:
            self.after_cancel(self.after_id_autosave)
        self.after_id_autosave = self.after(1500, self.save_config)

    def _filter_folder_list(self, event=None):
        """Filter folder list based on search bar"""
        search_term = self.folder_search.get().lower()
        self._populate_folder_list(search_term)

    def _populate_folder_list(self, search_filter=""):
        self.folder_tree.delete(*self.folder_tree.get_children())
        for item in self.automation_config:
            path = item[0]
            if search_filter in path.lower():
                short_name = os.path.basename(path) or path
                self.folder_tree.insert("", "end", iid=path, text=short_name, values=(path,))
            
    def _on_folder_select(self, event=None):
        selection = self.folder_tree.selection()
        if not selection:
            self.selected_folder = None
            self._populate_rules_list(None)
            self._update_settings_ui(None)
            return
            
        self.selected_folder = selection[0]
        
        rules = None
        settings = None
        for item in self.automation_config:
            if item[0] == self.selected_folder:
                rules = item[1].get("rules")
                settings = item[1].get("settings")
                break
        
        self.rules_title.config(text=f"AUTOMATION RULES FOR: {self.selected_folder}")
        self._populate_rules_list(rules)
        self._update_settings_ui(settings)

    def _populate_rules_list(self, rules_list):
        """Clears and fills right column with rules"""
        for widget in self.rules_container.winfo_children():
            widget.destroy()
            
        if rules_list is None:
            ttk.Label(self.rules_container, text="Select a folder to see its rules.").pack(padx=10, pady=10)
            return

        for rule_dict in rules_list:
            row = RuleEditorRow(self.rules_container, rule_dict, self._trigger_auto_save, self)
            row.pack(fill="x", pady=2, padx=2)
            
    def _add_folder(self):
        path = filedialog.askdirectory(initialdir=open_default_directory)
        if not path: return
        
        if any(item[0] == path for item in self.automation_config):
            messagebox.showwarning("Duplicate", "This folder is already in the automation list.", parent=self)
            return
            
        default_settings = {"enabled": False, "frequency": 60}
        self.automation_config.append([path, {"settings": default_settings, "rules": []}])
        self._populate_folder_list()
        self.save_config()

    def _delete_folder(self):
        """Delete folder from list"""
        selection = self.folder_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a folder to delete.", parent=self)
            return
            
        folder_path = selection[0]
        
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to stop automating '{folder_path}'?\n\n(This will NOT delete the actual folder on your disk, only the rules for it).", parent=self):
            self.automation_config = [item for item in self.automation_config if item[0] != folder_path]
            
            self.save_config()
            self._populate_folder_list()
            self._populate_rules_list(None)

    def _add_new_rule(self):
        if not self.selected_folder:
            messagebox.showwarning("No Folder Selected", "Please select a folder from the list first.", parent=self)
            return
            
        for item in self.automation_config:
            if item[0] == self.selected_folder:
                new_rule = {
                    "criteria": "Extension", "Operation": "equals", "Value": ".txt",
                    "Action": "Move", "Details": ""
                }
                if "rules" not in item[1]:
                    item[1]["rules"] = []
                item[1]["rules"].append(new_rule)
                
                self._populate_rules_list(item[1]["rules"])
                self.save_config()
                return

    def delete_rule_row(self, rule_row_widget):
        """Deletes rule"""
        if not self.selected_folder: return

        rule_to_delete = rule_row_widget.rule_data
        
        for item in self.automation_config:
            if item[0] == self.selected_folder:
                
                rules_list = item[1].get("rules", []) 
                
                if rule_to_delete in rules_list:
                    rules_list.remove(rule_to_delete)
                    
                    self._populate_rules_list(rules_list)
                    self.save_config()
                    return
                
    def _update_settings_ui(self, settings_data):
        """Update setting field"""
        if settings_data:
            self.setting_enabled_var.set(settings_data.get("enabled", False))
            freq_minutes = settings_data.get("frequency", 60)
            reverse_frequency_map = {v: k for k, v in self.frequency_map.items()}
            freq_text = reverse_frequency_map.get(freq_minutes, "Every 1 hour")
            self.setting_freq_combo.set(freq_text)

            self.setting_enabled_toggle.config(state="normal")
            self.setting_freq_combo.config(state="readonly")
        else:
            self.setting_enabled_var.set(False)
            self.setting_freq_combo.set("")
            self.setting_enabled_toggle.config(state="disabled")
            self.setting_freq_combo.config(state="disabled")

    def _on_settings_change(self, event=None):
        """Save changes"""
        if not self.selected_folder:
            return

        for item in self.automation_config:
            if item[0] == self.selected_folder:
                if "settings" not in item[1]:
                    item[1]["settings"] = {}

                freq_text = self.setting_freq_combo.get()
                freq_minutes = self.frequency_map.get(freq_text, 60)
                
                item[1]["settings"]["enabled"] = self.setting_enabled_var.get()
                item[1]["settings"]["frequency"] = freq_minutes
                
                self._trigger_auto_save()
                return

#region VIPs
class VIPsPage(tk.Frame):
    """Сторінка для відстеження важливих файлів (VIPs)."""
    def __init__(self, parent, controller):
        super().__init__(parent, bg=bg_c)
        self.controller = controller
        self.config_file = get_config_path("vips_config.json")
        self.tracked_files = {} 
        self.selected_file_path = None
        self.monitoring_active = False
        self.monitoring_thread = None
        
        self.frequency_map = {
            "Every 5 sec": 5,
            "Every 1 min": 60,
            "Every 10 mins": 600,
            "Every 1 hour": 3600,
            "Every 24 hours": 86400
        }

        # --- Top Panel (ОНОВЛЕНО) ---
        top_panel = ttk.Frame(self, style="TFrame")
        top_panel.pack(side="top", fill="x", padx=10, pady=10)
        
        # Ліва частина топа: Заголовок, Лічильник, Додавання, Видалення
        ttk.Label(top_panel, text="Tracked items", font=("Sans Serif", 14, "bold")).pack(side="left")
        self.count_label = ttk.Label(top_panel, text="(0)")
        self.count_label.pack(side="left", padx=5)

        ttk.Button(top_panel, text="+ Track", command=self._add_file).pack(side="left", padx=(20, 5))
        ttk.Button(top_panel, text="Delete", command=self._delete_file).pack(side="left", padx=5)

        # Права частина топа: Return і Start Service
        ttk.Button(top_panel, text="Return", command=lambda: controller.show_frame("StartPage")).pack(side="right")

        self.btn_start = ttk.Button(top_panel, text="Start Service", command=self._toggle_monitoring, style="Red.TButton")
        self.btn_start.pack(side="right", padx=10)


        # --- Main Content ---
        main_content = ttk.Frame(self, style="TFrame")
        main_content.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Ліва колонка
        left_frame = ttk.Frame(main_content, width=500)
        left_frame.pack_propagate(False)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        ttk.Label(left_frame, text="Search:").pack(fill="x", pady=(0,5))
        self.search_entry = ttk.Entry(left_frame)
        self.search_entry.pack(fill="x", pady=(0,5))
        self.search_entry.bind("<KeyRelease>", self._filter_files)

        # --- Створення таблиці та скролбарів ---
        # show="tree headings" покаже і дерево (ім'я), і заголовок для шляху
        self.tree = ttk.Treeview(left_frame, show="tree headings", columns=("path"), style="Dark.Treeview")
        
        # Створюємо обидва скролбари
        vsb = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(left_frame, orient="horizontal", command=self.tree.xview)

        # Підключаємо скролбари до таблиці
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.column("#0", width=200, minwidth=100, stretch=False) 
        self.tree.heading("#0", text="File Name")
        
        # Розміщення (порядок важливий для коректного відображення)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x") # <--- РОЗМІЩЕННЯ ЗНИЗУ
        self.tree.pack(side="left", fill="both", expand=True)

        # Налаштування колонок
        # #0 - це колонка з "плюсиком"/іконкою (основна назва файлу)
        self.tree.column("#0", width=200, minwidth=100, stretch=False) 
        self.tree.heading("#0", text="File Name")
        
        # Колонка шляху - робимо її широкою, щоб з'явився скрол, якщо вікно мале
        self.tree.column("path", width=1000, minwidth=200, stretch=False) 
        self.tree.heading("path", text="Full Path") # Додав заголовок, щоб було зрозуміло

        self.tree.bind("<<TreeviewSelect>>", self._on_file_select)

        # Права колонка
        right_frame = ttk.Frame(main_content)
        right_frame.pack(side="right", fill="both", expand=True)

        self.file_title = ttk.Label(right_frame, text="Select a file...", font=("Sans Serif", 12, "bold"))
        self.file_title.pack(anchor="w", pady=(0, 10))

        # --- Налаштування (Settings Group) ---
        settings_group = ttk.LabelFrame(right_frame, text="Tracking settings")
        settings_group.pack(fill="x", pady=(0, 10))
        
        settings_group.grid_columnconfigure(1, weight=1) 

        # 1. Enable Monitoring
        self.var_enabled = tk.BooleanVar()
        self.chk_enabled = ttk.Checkbutton(settings_group, text="Enable Monitoring", variable=self.var_enabled, command=self._save_current_settings)
        self.chk_enabled.grid(row=0, column=0, sticky="w", padx=5, pady=2, columnspan=3)

        # 2. Backups Toggle
        self.var_backup = tk.BooleanVar()
        self.chk_backup = ttk.Checkbutton(settings_group, text="Backups Enabled", variable=self.var_backup, command=self._save_current_settings)
        self.chk_backup.grid(row=1, column=0, sticky="w", padx=5, pady=2)
        
        # 3. Check Frequency
        ttk.Label(settings_group, text="Check every:").grid(row=2, column=0, sticky="w", padx=5)
        self.combo_freq = ttk.Combobox(settings_group, values=list(self.frequency_map.keys()), state="readonly", width=15)
        self.combo_freq.grid(row=2, column=1, sticky="w", padx=5, columnspan=2)
        self.combo_freq.bind("<<ComboboxSelected>>", lambda e: self._save_current_settings())

        # 4. Backup Destination
        ttk.Label(settings_group, text="Backup dest:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.entry_dest = ttk.Entry(settings_group)
        self.entry_dest.grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        self.btn_dest = ttk.Button(settings_group, text="...", width=3, command=self._browse_dest)
        self.btn_dest.grid(row=3, column=2, padx=5, pady=5)

        # Історія подій
        ttk.Label(right_frame, text="Event history").pack(anchor="w")
        history_frame = ttk.Frame(right_frame)
        history_frame.pack(fill="both", expand=True, pady=5)
        
        hist_vsb = ttk.Scrollbar(history_frame, orient="vertical")
        hist_hsb = ttk.Scrollbar(history_frame, orient="horizontal")

        self.history_list = tk.Listbox(history_frame, bg="#3C3F41", fg="white", borderwidth=0,
                                       yscrollcommand=hist_vsb.set, xscrollcommand=hist_hsb.set)
        
        hist_vsb.config(command=self.history_list.yview)
        hist_hsb.config(command=self.history_list.xview)

        hist_vsb.pack(side="right", fill="y")
        hist_hsb.pack(side="bottom", fill="x")
        self.history_list.pack(side="left", fill="both", expand=True)

        # (Блок кнопок знизу видалено, бо кнопки переїхали нагору)

        self.load_config()

    def on_show(self):
        self.load_config()

    def load_config(self):
        data = back.reading_profs(debug=False, path=self.config_file)
        if isinstance(data, dict) and "files" in data:
            self.tracked_files = data["files"]
            should_be_active = data.get("settings", {}).get("is_active", False)
        else:
            self.tracked_files = data if isinstance(data, dict) else {}
            should_be_active = False
            
        self._refresh_tree()
        
        if should_be_active and not self.monitoring_active:
            self._toggle_monitoring()

    def save_config(self):
        data_to_save = {
            "settings": {"is_active": self.monitoring_active},
            "files": self.tracked_files
        }
        back.writing_profs(self.config_file, data_to_save, debug=False)

    def _refresh_tree(self, search=""):
        self.tree.delete(*self.tree.get_children())
        count = 0
        for path in self.tracked_files:
            name = os.path.basename(path)
            if search in name.lower():
                self.tree.insert("", "end", iid=path, text=name, values=(path,))
                count += 1
        self.count_label.config(text=f"({count})")

    def _filter_files(self, event):
        self._refresh_tree(self.search_entry.get().lower())

    def _add_file(self):
        path = filedialog.askopenfilename()
        if path:
            if path in self.tracked_files:
                return
            
            self.tracked_files[path] = {
                "enabled": True,
                "frequency": "Every 1 min",
                "backups": True,
                "destination": os.path.join(os.path.dirname(path), "Backups"),
                "history": []
            }
            self.save_config()
            self._refresh_tree()

    def _delete_file(self):
        if not self.selected_file_path: return
        if messagebox.askyesno("Delete", f"Stop tracking '{os.path.basename(self.selected_file_path)}'?"):
            del self.tracked_files[self.selected_file_path]
            self.selected_file_path = None
            self.save_config()
            self._refresh_tree()
            self._clear_details()

    def _on_file_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        
        path = sel[0]
        self.selected_file_path = path
        data = self.tracked_files[path]
        
        self.file_title.config(text=os.path.basename(path))
        self.var_enabled.set(data.get("enabled", True))
        self.var_backup.set(data.get("backups", True))
        self.combo_freq.set(data.get("frequency", "Every 1 min"))
        self.entry_dest.delete(0, "end")
        self.entry_dest.insert(0, data.get("destination", ""))
        
        # Завантаження історії
        self._refresh_history_list(data.get("history", []))

    def _refresh_history_list(self, history):
        self.history_list.delete(0, "end")
        for event in history:
            self.history_list.insert(0, event)

    def _browse_dest(self):
        if not self.selected_file_path: return
        d = filedialog.askdirectory(initialdir=open_default_directory)
        if d:
            self.entry_dest.delete(0, "end")
            self.entry_dest.insert(0, d)
            self._save_current_settings()

    def _save_current_settings(self):
        if self.selected_file_path:
            self.tracked_files[self.selected_file_path]["enabled"] = self.var_enabled.get()
            self.tracked_files[self.selected_file_path]["backups"] = self.var_backup.get()
            self.tracked_files[self.selected_file_path]["frequency"] = self.combo_freq.get()
            self.tracked_files[self.selected_file_path]["destination"] = self.entry_dest.get()
            self.save_config()

    def _clear_details(self):
        self.file_title.config(text="Select a file...")
        self.entry_dest.delete(0, "end")
        self.history_list.delete(0, "end")
        self.var_enabled.set(False)

    def _toggle_monitoring(self):
        if not self.monitoring_active:
            self.monitoring_active = True
            self.btn_start.config(text="Stop Service")
            self.monitoring_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitoring_thread.start()
        else:
            self.monitoring_active = False
            self.btn_start.config(text="Start Service")
        self.save_config()

    def _monitoring_loop(self):
        """Розумний цикл: перевіряє кожен файл за його власним розкладом."""
        hash_file = get_config_path("vips_hashes.json")
        last_check_times = {} # { file_path: last_check_time_unix }

        while self.monitoring_active:
            current_time = time.time()
            
            # Копіюємо ключі, щоб уникнути помилки при видаленні під час ітерації
            for path in list(self.tracked_files.keys()):
                settings = self.tracked_files.get(path)
                if not settings: continue

                if not settings.get("enabled", True): 
                    continue

                freq_str = settings.get("frequency", "Every 1 min")
                interval = self.frequency_map.get(freq_str, 60)
                
                last_check = last_check_times.get(path, 0)
                if current_time - last_check < interval: 
                    continue 
                
                # Час перевіряти!
                last_check_times[path] = current_time 
                
                if settings.get("backups", False):
                    dest = settings.get("destination")
                    if dest:
                        # Викликаємо бекенд, отримуємо нові події
                        new_events = back.create_backup_on_change([path], dest, hash_file)
                        
                        if new_events:
                            # Оновлюємо історію в пам'яті
                            if "history" not in self.tracked_files[path]:
                                self.tracked_files[path]["history"] = []
                            
                            # Додаємо нові події на початок списку
                            self.tracked_files[path]["history"] = new_events + self.tracked_files[path]["history"]
                            # Обрізаємо до 50 останніх
                            self.tracked_files[path]["history"] = self.tracked_files[path]["history"][:50]
                            
                            self.save_config()
                            
                            # Якщо файл зараз відкритий, оновлюємо UI (через after, бо це інший потік)
                            if self.selected_file_path == path:
                                self.after(0, self._refresh_history_list, self.tracked_files[path]["history"])

            time.sleep(1)

#region Temporary
# Плейсхолдер
def writing_profs(dict_of_data, debug, path = None):
     """
     Проста функція для повного перезапису JSON-файлу.
     """
     if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "json_file.json")
     
     try:
          # Використовуємо 'w' (write) для повного перезапису файлу
          with open(path, 'w', encoding='utf-8') as json_file:
               # Додаємо indent=4, щоб JSON був читабельним
               json.dump(dict_of_data, json_file, ensure_ascii=False, indent=4) 
          if debug:
               print(f'Успішний перезапис файлу: {path}')
          return True
     except Exception as e:
          print(f'Помилка при спробі запису файлу {path}: {e}')
          return False

class RuleEditorDialog(tk.Toplevel):
    """Rule creation window"""
    def __init__(self, parent, available_destinations, available_criteria):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()
        self.title("Rule Editor")

        self.result = None

        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(main_frame, text="Criterion:").grid(row=0, column=0, sticky="w", padx=2)
        self.rule_criterion_combo = ttk.Combobox(main_frame, state="readonly",
                                                 values=available_criteria)
        self.rule_criterion_combo.grid(row=0, column=1, columnspan=2, sticky="ew", pady=2)

        ttk.Label(main_frame, text="Operator:").grid(row=1, column=0, sticky="w", padx=2)
        self.rule_operator_combo = ttk.Combobox(main_frame, state="readonly",
                                                values=["equals", "contains", "greater than", "less than"])
        self.rule_operator_combo.grid(row=1, column=1, columnspan=2, sticky="ew", pady=2)

        ttk.Label(main_frame, text="Value:").grid(row=2, column=0, sticky="w", padx=2)
        self.rule_value_entry = ttk.Entry(main_frame)
        self.rule_value_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=2)

        ttk.Label(main_frame, text="Destination:").grid(row=3, column=0, sticky="w", padx=2)
        self.rule_dest_combo = ttk.Combobox(main_frame, values=available_destinations)
        self.rule_dest_combo.grid(row=3, column=1, sticky="ew", pady=2)
        
        ttk.Button(main_frame, text="Browse...", width=8, command=self._browse_rule_dest).grid(row=3, column=2, sticky="w", padx=2)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=(10, 0))
        ttk.Button(btn_frame, text="Save Rule", command=self._on_save, style="Red.TButton").pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right")
        
        self.wait_window()

    def _browse_rule_dest(self):
        path = filedialog.askdirectory(initialdir=open_default_directory)
        if path:
            self.rule_dest_combo.set(path)

    def _on_save(self):
        criterion = self.rule_criterion_combo.get()
        operator = self.rule_operator_combo.get()
        value = self.rule_value_entry.get()
        destination = self.rule_dest_combo.get()

        if not all([criterion, operator, value, destination]):
            messagebox.showwarning("Incomplete Rule", "Please fill in all four fields.", parent=self)
            return
            
        self.result = {
            "criterion": criterion,
            "operator": operator,
            "value": value,
            "destination": destination
        }
        self.destroy()

#region Settings Menu

class SettingsMenu(tk.Frame):
    def __init__(self, parent, controller):
        bg_color="#2B2B2B"
        fg_color="#FFFFFF"
        active_color="#3C3F41"
        
        super().__init__(parent, bg=bg_color)
        self.controller = controller
        self.root=self.controller
        self.config_file = get_config_path("settings_config.json")
        self.settings_config={}

        # --- Variables (Must be at the top) ---
        self.lang_var=tk.StringVar(self)
        self.lang_var.set("English(default)")
        self.theme_var = tk.StringVar(self)
        self.theme_var.set("Dark") 
        self.boot_var=tk.BooleanVar(self)

        self.root.configure(bg=bg_color)

        # style setup for widgets
        style = ttk.Style()

        style.configure("TLabel", foreground=fg_color, font=("Arial", 16))
        style.configure("TMenubutton", foreground=fg_color, relief="flat", font=("Arial", 10), borderwidth=0)
        style.configure("TFrame")
        style.configure("Return.TButton", foreground=fg_color, font=("Arial", 10, "bold"), padding=5)
        style.map("Return.TButton", background=[('active', "#2B2B2B")])
        

        # Стовпець 0: Label (Settings) - вага 0, фіксована ширина
        self.grid_columnconfigure(0, weight=0)
        
        # Стовпець 1: "Розпірка" - вага 1, поглинає весь зайвий простір
        self.grid_columnconfigure(1, weight=1)
        
        # Стовпець 2: Кнопка Return - вага 0, фіксована ширина
        self.grid_columnconfigure(2, weight=0)
        
        # --- Header and Return Button ---
        self.settings_label=ttk.Label(self, text="Settings (currently in developing;))", font=("Arial", 24, "bold"))
        self.settings_label.grid(row=0, column=0, padx=20, pady=20, sticky="nw")

        self.return_button = ttk.Button(self, text="Return", style="Return.TButton", command=self.close_window)
        self.return_button.grid(row=0, column=2, padx=20, pady=30, sticky="ne")

        # -- General settings frame --
        self.general_frame = ttk.Frame(self, style="TFrame")
        self.general_frame.grid(row=1, column=0, columnspan=2, padx=20, pady=(10, 20), sticky="nw")
        self.general_frame.grid_columnconfigure(0, weight=1)
        
        # -General Header-
        self.general_label = ttk.Label(self.general_frame, text="General", font=("Arial", 16, "bold"))
        self.general_label.grid(row=0, column=0, columnspan=2, pady=(0, 15), sticky="nw")

        # --- Themes setup ---
        self.theme_options = ["Dark", "Light"]
        self.theme_menu_label = ttk.Label(self.general_frame, text="Themes", font=("Arial", 10))
        self.theme_menu_label.grid(row=1, column=0, padx=0, pady=5, sticky="w") 

        # Option Menu Themes
        self.theme_menu = tk.OptionMenu(self.general_frame, self.theme_var, *self.theme_options)
        self.style_option_menu(self.theme_menu, bg_color, fg_color, active_color) 
        self.theme_menu.config(width=18) # <-- Фіксована ширина
        self.theme_menu.grid(row=2, column=0, padx=0, pady=2, sticky="w") 


        # --- Language Setup (Рядки 3 та 4) ---
        self.lang_options=["English (default)", "Deutsch", "Українська", "Français"]
        self.lang_menu_label = ttk.Label(self.general_frame, text="Language", font=("Arial", 10))
        self.lang_menu_label.grid(row=3, column=0, padx=0, pady=15, sticky="w") 
        
        # Option Menu Language
        self.lang_menu = tk.OptionMenu(self.general_frame, self.lang_var, *self.lang_options)
        self.style_option_menu(self.lang_menu, bg_color, fg_color, active_color) # <-- Розкоментовано
        self.lang_menu.config(width=18) # <-- Фіксована ширина
        self.lang_menu.grid(row=4, column=0, padx=0, pady=2, sticky="w") 


        # --- Joint booting with system (CheckButton) ---
        self.boot_check=tk.Checkbutton(self.general_frame, 
                                       text="Synchronise booting with system", 
                                       variable=self.boot_var,
                                       bg=bg_color,     
                                       fg=fg_color,     
                                       selectcolor=bg_color, 
                                       activebackground=active_color)
        self.boot_check.grid(row=5, column=0, pady=(15, 0), sticky="w")


    def style_option_menu(self, menu_widget, bg, fg, active_bg):
        menu_widget.config(bg=active_bg, fg=fg, 
                           activebackground=active_bg, 
                           activeforeground=fg, 
                           relief="flat", 
                           borderwidth=1,
                           highlightbackground=bg,
                           highlightcolor=fg,
                           highlightthickness=1)
            
        #Pop-out window stylization
        menu_widget["menu"].config(bg=bg, fg=fg, 
                                 activebackground=active_bg, 
                                 activeforeground=fg)

    def close_window(self):
        print(f"Збережено налаштування: Тема={self.theme_var.get()}, Мова={self.lang_var.get()}, Автозапуск={self.boot_var.get()}")
        self.controller.show_frame("StartPage")


if __name__ == "__main__":
    app = App()
    app.mainloop()
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

#region End, Credits:

"""
|
|On this project worked:
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|   @Romart008 -    Frontend - UI for Sorting, Logging, Automatization, VIPs, Desktop pages;
|                   Backend - implementation of JSON configurations
|
| *+==:.....                         .....:===*
| ***=:.....                .:--**+*=:....:=***
| *++=:.....              -:=#%%*.   .....:===+
| *=+=:-:...           :-=*%%%#.     ...:--====
| +++==:....         :*==+*%%%=       ..::-====
| #*+=::.:#%%%+:   -*=*#%%%%%*       ...::-=+*#
| +=*+:::.-%%%%%%%*=+*#%%@@@%:       ....:-=***
| **++::::. -*###%#%%%%*#%@@%:       ...:::=++*
| ***+-::..   .=**##*#%@%%%%%:       ....:==***
| ***+-:::..     :#*#%%%%@@@@%#-     ...:::=***
| ***+-:::..      *#%%%%%@@@%%###+: ...:-::+++*
| ##*+-::...      =#%%%%%%@@#:   .:....::-=+**#
| #*++-::...        .*#%%@%%@@%%%=   ..:::-+++*
| ***+-::::....    =%%%%%%**#%%%%*:. ..:::-====
| *=:+=::::...    :#%%%%%@%**#%%@@%#:.:=::-++=+
| **===-:::....  ==+%@@%%%%%%%%@@%%+-::::::==+*
| #*=+=---::... =##%%%%%%%%%%%@@@%%%*#**#****##
| ***+-::-::...:#%@%%%@@@%%@%%@@@@%@@%%%#%%%%##
| #+::-::::-:::*%%%%%%%@%@@%%@@@@@@%@@%%%%%#%%%
| #**======::-*@@%%%%@%%@@%%@%%@@@@@%@@@%%%%##%
| %##*++===-=%@@@%%%%%@%%%%%%%%@@@@@@%@@@%%%%%%
| *****+===+%%%@@%%%%@@@@%**#%%@@@@@@@@@@@@@%@%
| %%#+==+==+#%%@@@@@@@@%%%@%%%@@@@@@@@@@@@@%+%@
| %*+*%%=+%%@@@@@@@@%%%%%%@@@@%@@@@@@@@@@%%%@@@
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|   @getmandoroshenko228 - Frontend - UI for Renaming and Settings menu
|
|                                                                                                     
|                        @                                                                           
|                                                                                                    
|                          %%%%                                 @@@@@                                
|                           %%@@@@@@                         %%%%%@@                                 
|                           %@@@@@@@@%          @@@       %%%%%%%%                                   
|                         %%%%@%%@@@@@@%%%  %%@@@@@@@@%%@%%%@ %%%                                    
|                         %%% %%%@@@@@@@%@@%%%%@@@@@@@@%%%  %%%%                                     
|                            %%%@@@@@@@%%@%%%%%@@@@@@@@@%%%%@@@@                                     
|                      %@@@@@@@@@@@@@@%%%%% %%%%%@@@@@@@@@@@%@@                                      
|                     @@@@@@@@@@@ @@@@@@@%@%%  @%%%@@@@@@@@@@@                                       
|                     %@@@@@@@@@  @@@@@@@@@@@@@   %%%%%%@@@@@                                        
|                     @@%@@@@@@  %@@@%%@@@@@@@@@@@  %%%%%%@@@                                        
|                     @@@@@@@@    %@%%%@@@@@@@@@%%@%%%%@@%%%@                                        
|                     @@@@@@@    @@@@@@ @@@@@@%%%%%@@@@%%%%                                          
|                     @@@        @@@%@%%%%%@@@@@@@@@@@@%%%%%                                         
|                     @@            @@%%@@@@@@@@@@@@@@@@%%%%%    %%%%%                               
|                     @@      @@      @@@@@@@@@@@@@%@@@@@@@%%    %%%%%%                              
|                      @               @@@@@@@@@@@@@@%%@@@@%%%% %%%%%%%%%%%%                         
|                                        @@@@@@@@@@@@@@@@@@%%@%%@@%%%%%%%%%%%%                       
|                                       @@@@@@@@@@@@@@@@@@@@%@%%%@@@@%%%%%%%%%%                      
|                                        @@@@@@@@@@@@@@@@@@@%  %%@@@@@%%%%%%%%%%           %%%%%%    
|                                          @@@@@@@@@@@@@@     %%%%@@@@@%%%%%%%%%%                    
|                                            @@@@@@@@@         %%%@@@@@%%%%%%%%%%% %%%               
|                                                        %@@%%%%%%%%%@@%%%%%%%%%%%%%@%%@@@@@         
|                                                         @@@%%%%%%%%%@@%%%%%%%%%%%   @%@@@@%@@      
|           @@                                          @@@@@%%%%%%%%%%%%%%%%%%%%%%  @@%%% @%%%%@    
|             @%    @%                                  @@@@%%%%%%%%%% %%%%%%%%%%%@@@@@  @@@@  %@%%%%
|            @@% %%@@@@                               @@@@@@%%%%%%%%%%%     %%%%%%@@@@@@@@@@@@@@   %%
|         %%%%%%% %@@@@@                            @@@@@@@@%%%%@@%%%%%%    %%%%%@@@@@@@@@@@@@@  @   
|         %% @@@%%%@@@@@@                           @@@@@@@%%%%%%@%%%%%%     %%@@@ @@@@@@@@@@@@@@@   
|             @@@@%@%@@@@                          @@@@@@@%%%%%%%%%%  %%%%   %%%%      @@@@@@@@@@@@@ 
|     %      %%%@@@@@%@@@@                       @@@@@@@@@%%%%%%%@%%%%%%%%%  %%%          @@@@@@@@@@@
|      %%    %@@@@@@@@@@@@@                    @@@@@@@@@@@%%%%%%%@@@%%%%%%%%%%%%           @@@@@@@@@@
|        @@ @@@@@@@@@@@@@@@                  @@@@@@@@@@@@@@@@%%%%%@@@@%%@%%%%%%             @@@@@@@@@
|       @@@@@@@@@     @@@@@@@             @@@@@@@@@@@@@@@@@@@%%% %%@@%%%@%%%                  @      
|    @@@@%%%           @@@@@@@@          @@@@@@@@@@@@@@@@@@@@@@%%@@%%%@@@%%                          
| @@@@@                 %@@@@@@@@@@@@@@ @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%                          
|                          @@@@@%%@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                            
|                             @@@@%%@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                                 
|                               @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@                                      
|                                @@       @@@@@@@@@@@@                                               
|                               @           @@%@@@                                                   
|                                              @                                                     
|
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|   @teforteem79 - Backend - functionality of Sorting and Desktop menus
|
|                                              @@@                
|                                          @@@*@@     @@@         
|                                       @@%.:@@     @@-@          
|                                    @@@...@@     @@-.%@          
|                                  @@%...@@     @@=..:@           
|                                @@%...=@@    @@+... @@           
|                               @@.   @@    @@%    .#@            
|                             @@+.  .@@    @@...   =@             
|                            @@.   .@@   @@:.     :@              
|                           @@.   .@@  @@#.      .@@              
|                          @@.   .*@ @@%.       .@@               
|                          @..   .-@@+.        .@@                
|                         @=.       ...       .@@                 
|                        @@.                 -@@                  
|                        @+.               .%@                    
|                        @..              :@@                     
|                        @ @%     @@    .@@                       
|                        @ @@@  @@@@%  %@@                        
|                        @@ @%  @@@  @@@                          
|                         @  *   *  #@@                             
|                         @@#*######@@                            
|                           @@####%@@                      @%+=@@ 
|                           @@####%@@                    @@@+@%#@ 
|                          @@#@#@#%%@@               @@@*+@@@@@@  
|                        @@@%#@##@##@#@@@        @@@#=%@@         
|                      @@#@@##@###@##%@##@@@ @@@%=#@@             
|                    @@##@%###@####@####@%#@@**@@@                
|                   @@##@####%%#####@#####@@#%@                   
|                  @@##@#####@#######@%#####@@#@                  
|                 @@##@######@*#######@@###*%@@@                  
|                  @@@%#####@%#########@@*@@@@@                   
|                     @@@@@%@####*#@@@@@@@@                       
|                    @@+---#@@@@@@ @@@@@                          
|                @@@=--#@@     @@@  @@@                           
|             @@@--#@@          @@  @@@                           
|          @@*-#@@              @@@  @@                           
|       @@=*@@                   @@  @@                           
|    @@@@@                       @@  @@                           
| @@@@                           @@  @@                           
|                                 @  @@                           
|                                 @  @@                                
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|   @mailicynk - Backend - functionality of Renaming menu, implementation
|   of background program execution, Windows tray, and renaming configuration
|
| ....=#####:............................................................
| ....-####%*............................................................
| ....-#####%=...........................................................
| ....-#####%%:..........................................................
| ....:######%*..........................................................
| ....:######%#-.......................................................::
| ....:####*#%%*:.....................................................+##
| ....-####*##%#=...................................................-####
| ....-####*####*:.................................................###%#-
| ....-####*#####+...............................................=#####=:
| ....-####*#####%:............................................:+#####**#
| ....:#*****######...........................................=##%######%
| =....-##**######%=........................................:*#%%#####%%%
| #*=+*+:+#*########:......................................=#%%##%##%%%%%
| %##%%%%*::=#######+....................................:##%##%###%%%%#:
| %%##%%%%%+=########-..................................+##########%%*-..
| %%%%#%%%###########+................................:*##%#%%###%%#=....
| %%###############**#-..............................-*#%%%########**##=.
| ############%%###**#*:............................=#%%%%#######%%%%%%-.
| %#####%%###%%%%%####%+..............:::..........*#%%####%##%%%%%%%%+..
| #####%%%%###%%%%%##*=--............::::::......-*#%%####%%%#%%%%###=...
| #######%%%##%%%%%%##=-=-....::....:::::::..::.-*###%############*=.....
| ########***#%%%%%%#%*=*=.....:.......::::..::=*######**##########%#=...
| ####%%####*#%%%%%%#%#==*:...................=*######*####%##%#####%#-..
| *******##%##%%%%%##%#+-*#-...::::::::::::::=**####%#####%#########%+...
| *####***#%%#%%%%%##%%+:=%%=....:::::-::::::**############%%###*+-:.....
| **##########%%%%%%#%+-:-+%*:::::::::::::::-*################%%%#:......
| *#########*#%%%%%%%%+-:--*%-::::::::-=---:-**####*##****##%%#:.........
| *###########%%%%%%#%*-::-*%=::::::-=++==--+*#####**########*-..........
| ***#########%%%%%%%%+----=%*:::::-*#####*=+*##############-............
| ############%%%%%%%%+=----:#-...:#*#+=*####*########**###=.............
| ############%%%%%%%%*=---+::#.::+%#+-+*#%%%*########*****=.............
| *****#######%%%%%%%%*:-=+=:.+=.-+#*--=%#%%%%##########**=..............
| ***********#%%%%%%%%##+++-..:+:.:#*=#%%%%%%%######***#*+...............
| ***********#%%%%%%%%%#*==-...=+..+##%%%%%%%%%####**####+:..............
| ***********#%%%%%%%####*+-::.-*==*######%%%%%%####**#***-.........:....
| ***++******#%####%%%#####+:::===+###%%%%%%%%#**###******=........:::...
| *++++******#####%%%##*####*==+*-:=#######%%%+************-.......::::..
| +++**+*****#%###%%%#######*+*####=-**++****#***********+:........::::::
| ==++++*****#####%#%#####*+**#**=+*-::===++*##****+******=:.......::::::
| :--=+++++**############*+-+#=::::*=+=-=---:=******+++++==:.......::::::
| :--=++++++*############**#%+-=---=*+=-:=-:-+*****++++++=::.......::-:::
| ---=+++++*####%###########=---::-+*--::-=+**+++++++++++=::.......:-:::
| ---=+++++++################+:--:..-*+::.--++++++++++++-::...........---
| -------++++######%%#%%#####*.::::--+*-::--=++++++++++++:.............:-
| -----:+++++######%%##%#####*++-:.:-+#*#+==-++++++++-::::::::::::::::::-
| -----:-===+######%##%%######+-:.:::+##*+++=++++++=-::::::::::::::::::--
| -----::::-+###%#%#####%####%=-:...:+=*+=++=-::..:..::::::..........----
| ------::::-###%%%#####%####%=:....:=::%+=-::......:::::::..........----
| -------::::###%%%%*:+######%+-:...--..**==:::.....:::::::::==:::::.----
| -------:::-%%%%%#-..-#####*#*+-:...:::+*+==-:....:::::::::::===::====-=
| --------:..+%%#=.....*####*##+==-...:-++*=--....::::::::::::.:==:.=====
| -------::...--.......-%###*##*====:.::==*=.:::-:::::::::::-=:.:-=:.-===
| -------::::..........:#####*%#+--==:..:=+*--::--:.:----==-.:=-::--.:--=
| ------:..............:######%#**+-:.-+--=+*:....-..-:::---=-==-::--:---
| ......................#*##%%%##***=-::==+=:-::---.-+=-..::--:--::::::-:
| --::::::::...::..::..:##%%%%#%#*=.:-=--:=++------=-::++=+-:.::::-::-:::
| --:::........:::::::::%%%%%%#%#*+:::=----=-*+-=-::--:-=+==+-.:-------::
| --:........:::::::::::##%%%##%%#*=::=-:--:-+%+-:-.::=====-=:-----------
| --:........::::::::::-%###%##%%##+--=+-==-==*%=::--..-:=-=--=--:::-----
| --:..::::..::::::::::-###%%%%%%##+-==+++===-+#*=--:--:----=+=-=-==-----
| =--::.:.....:::::::-=*####%%%%%%#+--===+==+*+=-++==-.:--::-=+==---==---
| ===--::.....:----=*###%%%%%@@%%%#+====+#*++=-----=--::-+**=---+-::-----
| =----::.....:--+########%%%%%####*+**+#*###*==-==--::.:::::..:-=++==+=-
| ::::.:::=*##############%%%%%####+=*####++=-==+=+*+-=--::-.....:==++++*
| .::::-:-==++++#%############%%%%%###%%%#*+*+++****+**+**++===------===-
| --=-:=++======*%%##########%%%%%%%%%%%%%%%%%%%##**++++*++++++++++++++++
| .:----==-:-:::-*#***********####%%%%%%%%%%###############***+==-::::::.
| ..............................::--==++****##################%####+*****
|
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|   @Kelner-r - Backend - functionality of Automatization and VIPs menus
|
|        %#################################################################################%%@      
   @%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%@   
  @@@%%*-.................................................................................:-+%%%%%@
 @@@%*=-:..................................................................................................-%%%%@
@@@@**++++++++==:....:-----:::::......................:::------------------------------------...-@%%@
@@@@-:==--=+++++=:..:::-:::.....................::::::::::-----------------------------------::-%@%@
@@@@-::....-==+++==::...................:::.-+-+**+--==++**+--:-==-----------------::::-----=--#@%@
@@@@-:::...:::-==+==.:.............:-=+===++++++=-#+********+#=+*****+==-------------------==---#@%@
@@@%-:::...::----===:::.......:---==+#++++****++=#@#**++=--:-+#@%#*=+****+++----------------------#@%@
@@@%---:...:------==.:-::...:-===+=*@%*########%@%###########*@%%######+-=*+#*+=-==----------------#@%@
@@@%--:...::::--::-...:.:+--=+####*%%@**######%@%###*######%%@%##########%%#**##=----------------#@%%
@@@%-::...::::-:::...-+##%@++*#######%%%##%%%%%%%%%#%#%###*+****##%%%####%@%%+*##*+=--------------#%%%
@@@%++====:----::.-+*##%%%%%**#%%%%%%%%%%%%%%%%%%###*+==-----------+#%%###*###**=------===-----#@%%
@@@=----======--=-=+*#%%%%%%%%%%%%%%%%############**+====-------::::::+%####%####*=---=====----#%%%
@@@%--:::-::-===*%##%%%#############***#############*+====--------:::::::%%%%%%#*#*=-========----#%%%
@@@%--:::-:.:::=*##%#****######********#********#**++++****++=--:::::::::*@%%#=###+-========+---#%%%
@@@%---::::.:::+*#%%*++****++****++++++++************++=--::::::*###+##%======+++-===-#%%%
@@@%=---:::.::=#%%%+===++++****+++++++-+*+=====++++++************++-::::::-###%###*==+*****+*===#%%%
@@@%=---:::..:+#%*-==+++********++++++++===+-::::--==+++************+=-----*#####*#++********===#@%%
@@@%=--::::.:=*##--=++****++++++++++***#*-::::.::-==+****************++====%%%%%%##*+********+==#%%%
@@@%=--::::..=*##-=++++*************#####=:::::::::-=+*++===++**##****++==%%%#*+##*+********+==#%%%
@@@@-----::::=*#%#===+++++****##%%%%%*-:::::::::::::-**+==-----=*###**++=---%###=####=+*******=-=#%%%
@@@%=---=-::+#%%@@#++****#########%%#::---::::::::::-@@@@@%#+=---=**#*++=--+####=##%#+++*+*=+=-=#@%%
@@@%=======-=*##%@@#*+**##%%@@@##+#+=====---:::::::::+#+##@@%*#=+#%#+===---####*##%%=+++=--=-=#@%%
@@%+========+*##@@@#*****++=#*@@@%==+**++===--:::::::::=+*###=:::::::----+#%*########++=====---=#%%@
@@%+++===-+*##@@#**++*+=-+**=-=+*****++===--::---:::::::::--::::::.:::+#%**####*#*+==++=--==#@%@
@@@+======-+##%@@%*=========++=++-=+********++==--=-::::::::::::::::::::::-*#@@@@%#*##**++==---=#@%%
@@@%+=----==*#%%@@=-------=++=++*++************+=-::::::::::::.....:::::::::::::=###+#%#%#*+====---=+#@%%
@@@%**++====##%%%-------==+++*+*##%#*#####+----:::::::::::::::::.......::::-###+#%#=---=====--+=#@%%
@@@%+++++++*###%---====--===+============--------:-:::::::::::::::::::::.::.....::::::-------==--=+=#@%%
@@@%+++++++######-=----==++++======--===-------:::::::::::::::::::::::::::::::::--------==---+==#@%%
@@@%+++++++%#%*---===++++=========-:+++=-------:::::::::::::::::::::::::::::::::::::---=---=*+==#@%%
@@@%+===-----==++++++++++++++++===--*#*+=--------::::::::::::::::::::.:::::::::::::--------=***==#%%%
@@@%+++=++++++++++++++++++++++++++==:*###*+=-------:::::::::::::::::::::::::::::::---=++++***==#@%%
@@@%++++++++****+++++++*++++++++++++=:=*%%%%*++=-------::::::::::::::::::::::::::::-=*##*++++++===#%%%
@@@%*++****++++++++****++***+++++++==*#######********+++===---------::::::::--==+*#%###++=++++===#%%%
@@@%********************************###########****************************###%%%###++==+++==#%%%
@@@%****************************#####################################***#####%%######%%*==+=+=+===#%%%
@@@%++********************#########################*###########%%%%%%%######***%#%###**#*==++++===#@%%
@@@%+==++****#########################****************************#######****++==*@@@@%###*==+=--=--=#@%%
@@@%***+==+**##################********************++++====----==++********++=-----#%+##%%##+===---====#%%%
@@@@=+**+=+%%%@#+++********************++====---------:::::::::::-------:::::-+#*####%%#+++=+++=--#%%%
@@@@===*+-*%%%@#++++************++====-----------:::::::::::::::::::::::::-*#####%%%#*+======---#%%%
@@@%===-=+%@@@@#++===+++++***+++=====-----------:::::::::::::::::::::::::--*#%##%%%%%*****++=---#@%%
@@@%*====+*+=%@%*+===+++++++++++====------------:::::::::::::::::::::::::--+%%%%%%+##********+==#%%%
@@@%**++#%*+=%%%*+==+++++++++======-----------::::::::::::::::::::::::::---*%@@@%#%********+==#%%%
@@@*++#*+#++%@*++==++++++=========------------:::::::::::..::::::::::::::-----+%*%%%%*********+==#@%%
@@@%*++=+=%%@@@*++==+++++=========------------:::::::::::...::::::::::::::-----%+%%%%%#********+==#@%%
@@@%##*#*+#+++*%%++=+++++========------------:::::::::::...:::::::::::::-----=%#%%%%#********+==#%%%
@@@%###%%%##***#%*+++++++======---------------:::::::::::...::::::::::::------+%%%%%%***********+==#%%%
@@@%###%%%%%######****+++=====-------------::::::::::::...::::::::::::------=#%%%%#%********+==#%%%
@@@@###%%%%%%%%######********+=======-----------::::::::::..:::::::::::------=+@@@@%%##********+==#%%%
@@@%###%%%%%%%%%%#######***++****++++======--------:::::::.::::::::::------==@%%%*%%%%%####*****+==#%%%
@@@%###%%%%%%%%%%%%%########*++*##********++++=====------:::::::::------==%%%%%%%%%%%%%#%%####*+==#%%%
@@@%###%%%%%%%%%%%%%#############*++++######****+++++====---:::--------===#@%%%%%%#%%%%%#####*++#%%%
@@@%###%%%%%%%%%%%%%%%#################***++*#######****++++==----------=====%@%%%@%%####@@%%%%%%%+++#@%%
@@@%###%%%#*++#%%%%###%%###############****+++*#######********+=-----========+%@@@@@%#####%@@%%%%**+#%%%
@@@%*###%%+===--#%#######%%%###############**=++#######*****+======+*+====*%@%%%*##########-:-+%++#@%@
@@@%*##%%%+==--=+#%%##########%%%####################***++*#########****##*++====*@@%%%#%%#######*+-::=*++#@%@
@@@%####%%%#+-===*%%#%##########%%####################*++*#%%%######*++======*@%%%%%@@%########*:.-***#%%@
@@@%###%%%%%%#==+%#%%################%%%%#################*+*###++========+%@@@@@@@%#########*#%***#@%@
@@@@****%%%%%%+*%%%####################%%%%%%%%%#############+**+==========+%###+#@@@%######*%%####%@@@
@%%@*:::=%%%%%###########################%%%%%%%%%###############%**+==++++%%%%+@@@@%#############%%%@%@@
@%%%%#--++===---::--===============================================----:-========++=-::::::--=*#%%@@@@@
 %##%%@%#+++==----===============================================================+++==--------=*%@%@@@@
   %%%%@@%@@%@@@@% ...   
     @@%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%@@     
|
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------
|   @omykytyn543 -  Backend - functionality of Logging menu
|                   Design - visuals for every menu 
|                   Webdesign - website creation
|
|  *your ASCII signature here*
|
|------------------------------------------------------------------------------------------
|------------------------------------------------------------------------------------------

"""
