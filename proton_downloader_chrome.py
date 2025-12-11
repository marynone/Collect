import os
import time
import random 
import glob 
import json 
import zipfile # <--- NEW: for creating zip files
import requests # <--- NEW: for interacting with Telegram API
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException

# Define the selector for the modal backdrop which causes the click interception error
MODAL_BACKDROP_SELECTOR = (By.CLASS_NAME, "modal-two-backdrop")
CONFIRM_BUTTON_SELECTOR = (By.CSS_SELECTOR, ".button-solid-norm:nth-child(2)")

# Constants
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloaded_configs")
SERVER_ID_LOG_FILE = os.path.join(os.getcwd(), "downloaded_server_ids.json") 

# --- CRITICAL CHANGE ---
# TARGET_COUNTRY_NAME is now None to process all countries.
TARGET_COUNTRY_NAME = None 
# ------------------------

MAX_DOWNLOADS_PER_SESSION = 20 # Maximum downloads before relogin (UNCHANGED)
RELOGIN_DELAY = 120 # Delay in seconds between sessions to cool down the IP (2 minutes)

# Environment variables will be read once at runtime
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Create the download directory if it doesn't exist
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)
    print(f"Created download directory: {DOWNLOAD_DIR}")


class ProtonVPN:
    def __init__(self):
        self.options = webdriver.ChromeOptions()
        
        # --- Optimization for GitHub Actions/Server Environments ---
        self.options.add_argument('--headless')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-gpu')
        self.options.add_argument('--window-size=1920,1080')
        
        # *** Key Configuration: Setting the Download Path in Chrome ***
        prefs = {
            "download.default_directory": DOWNLOAD_DIR,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True 
        }
        self.options.add_experimental_option("prefs", prefs)

        self.driver = None

    def setup(self):
        """Initializes the WebDriver (Chrome) with Headless options."""
        self.driver = webdriver.Chrome(options=self.options)
        self.driver.set_window_size(1936, 1048)
        self.driver.implicitly_wait(10)
        print("WebDriver initialized successfully in Headless mode (Chrome).")

    def teardown(self):
        """Closes the WebDriver."""
        if self.driver:
            self.driver.quit()
            print("WebDriver closed.")

    def load_downloaded_ids(self):
        """Loads the set of previously downloaded server IDs."""
        if os.path.exists(SERVER_ID_LOG_FILE):
            try:
                with open(SERVER_ID_LOG_FILE, 'r') as f:
                    return set(json.load(f))
            except json.JSONDecodeError:
                print("Warning: Log file corrupted. Starting with an empty list.")
                return set()
        return set()

    def save_downloaded_ids(self, ids):
        """Saves the set of downloaded server IDs."""
        with open(SERVER_ID_LOG_FILE, 'w') as f:
            json.dump(list(ids), f)
            
    def login(self, username, password):
        try:
            self.driver.get("https://protonvpn.com/")
            time.sleep(1) 
            self.driver.find_element(By.XPATH, "//a[contains(@href, 'https://account.protonvpn.com/login')]").click()
            time.sleep(1) 
            user_field = self.driver.find_element(By.ID, "username")
            user_field.clear()
            user_field.send_keys(username)
            time.sleep(1) 
            self.driver.find_element(By.CSS_SELECTOR, ".button-large").click()
            time.sleep(1) 
            pass_field = self.driver.find_element(By.ID, "password")
            pass_field.clear()
            pass_field.send_keys(password)
            time.sleep(1) 
            self.driver.find_element(By.CSS_SELECTOR, ".button-large").click()
            time.sleep(3) 
            print("Login Successful.")
            return True
        except Exception as e:
            print(f"Error Login: {e}")
            return False

    def navigate_to_downloads(self):
        try:
            downloads_link_selector = (By.CSS_SELECTOR, ".navigation-item:nth-child(7) .text-ellipsis")
            WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable(downloads_link_selector)
            ).click()
            time.sleep(2) 
            print("Navigated to Downloads section.")
            return True
        except Exception as e:
            print(f"Error Navigating to Downloads: {e}")
            return False

    def logout(self):
        try:
            self.driver.get("https://account.protonvpn.com/logout") 
            time.sleep(1) 
            print("Logout Successful.")
            return True
        except Exception as e:
            try:
                self.driver.find_element(By.CSS_SELECTOR, ".p-1").click()
                time.sleep(1)
                self.driver.find_element(By.CSS_SELECTOR, ".mb-4 > .button").click()
                time.sleep(1) 
                print("Logout Successful via UI.")
                return True
            except Exception as e:
                print(f"Error Logout: {e}")
                return False

    def process_downloads(self, downloaded_ids):
        """
        Processes downloads for ALL countries, limited by MAX_DOWNLOADS_PER_SESSION.
        Returns (all_downloads_finished, downloaded_ids).
        """
        try:
            self.driver.execute_script("window.scrollTo(0,0)")
            time.sleep(1) 

            try:
                # Click OpenVPN/WireGuard tab
                self.driver.find_element(By.CSS_SELECTOR, ".flex:nth-child(4) > .mr-8:nth-child(3) > .relative").click()
                time.sleep(1) 
            except:
                pass
            
            print(f"Found {len(downloaded_ids)} server IDs already logged as downloaded.")

            countries = self.driver.find_elements(By.CSS_SELECTOR, ".mb-6 details")
            print(f"Found {len(countries)} total countries to check.")
            
            download_counter = 0
            all_downloads_finished = True 

            for country in countries:
                try:
                    country_name_element = country.find_element(By.CSS_SELECTOR, "summary")
                    country_name = country_name_element.text.split('\n')[0].strip()
                    
                    # --- NEW LOGIC: Check if session limit is already reached ---
                    if download_counter >= MAX_DOWNLOADS_PER_SESSION:
                        print(f"Session limit reached ({MAX_DOWNLOADS_PER_SESSION}). Stopping for relogin...")
                        all_downloads_finished = False 
                        return all_downloads_finished, downloaded_ids
                    # -----------------------------------------------------------
                    
                    print(f"--- Processing country: {country_name} ---")

                    self.driver.execute_script("arguments[0].open = true;", country)
                    time.sleep(0.5)

                    rows = country.find_elements(By.CSS_SELECTOR, "tr")
                    
                    # Check if all configs in this country are already downloaded
                    all_configs_in_country_downloaded = True 

                    for index, row in enumerate(rows[1:]): # Skip header row
                        
                        try:
                            file_cell = row.find_element(By.CSS_SELECTOR, "td:nth-child(1)")
                            server_id = file_cell.text.strip()
                            
                            # --- CRITICAL CHECK: Skip if Server ID is logged ---
                            if server_id in downloaded_ids:
                                # print(f"Skipping config (Server ID: {server_id}). Already logged.")
                                continue
                            
                            # If we found one config NOT downloaded, the country is NOT finished
                            all_configs_in_country_downloaded = False
                            
                            # --- Check session limit AGAIN before attempting download ---
                            if download_counter >= MAX_DOWNLOADS_PER_SESSION:
                                print(f"Session limit reached ({MAX_DOWNLOADS_PER_SESSION}). Stopping for relogin...")
                                all_downloads_finished = False 
                                return all_downloads_finished, downloaded_ids
                            # -----------------------------------------------------------

                            btn = row.find_element(By.CSS_SELECTOR, ".button")

                        except Exception as e:
                            print(f"Could not determine Server ID/Button for row {index} in {country_name}. Error: {e}")
                            continue 

                        random_delay = random.randint(60, 90) 
                        
                        # --- Execute Download ---
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(0.5)

                            ActionChains(self.driver).move_to_element(btn).click().perform()

                            confirm_btn = WebDriverWait(self.driver, 30).until(
                                EC.element_to_be_clickable(CONFIRM_BUTTON_SELECTOR)
                            )
                            confirm_btn.click()

                            WebDriverWait(self.driver, 30).until(
                                EC.invisibility_of_element_located(MODAL_BACKDROP_SELECTOR)
                            )
                            
                            download_counter += 1
                            print(f"Successfully downloaded config (Server ID: {server_id}). Total in session: {download_counter}. Waiting {random_delay}s...")
                            time.sleep(random_delay) 

                            # --- CRITICAL: Log the Server ID as downloaded ---
                            downloaded_ids.add(server_id)
                            
                        except (TimeoutException, ElementClickInterceptedException) as e:
                            print(f"CRITICAL ERROR: Failed to download config {server_id} in {country_name}. Rate limit or session issue detected. Shutting down session.")
                            all_downloads_finished = False
                            return all_downloads_finished, downloaded_ids
                        
                        except Exception as e:
                            print(f"General error during download {server_id} in {country_name}: {e}. Shutting down session.")
                            all_downloads_finished = False
                            return all_downloads_finished, downloaded_ids
                            
                    if all_configs_in_country_downloaded:
                        print(f"All configs for {country_name} were already downloaded. Moving to next country.")
                    else:
                        print(f"Completed download attempts for {country_name} in this session.")
                        
                except Exception as e:
                    print(f"Error processing country block for {country_name}: {e}. Continuing to next country.")
                    
            # If the loop finishes without hitting the session limit, all downloads are complete.
            all_downloads_finished = True 

        except Exception as e:
            print(f"Error in main download loop: {e}")
            all_downloads_finished = False
            
        return all_downloads_finished, downloaded_ids

    
    def organize_and_send_files(self):
        """
        Organizes downloaded files by country and sends a zip file for each country via Telegram.
        """
        print("\n###################### Organizing and Sending Files ######################")
        
        # 1. Group files by country code (e.g., "US", "JP", "CH")
        country_files = {}
        for filename in os.listdir(DOWNLOAD_DIR):
            if filename.endswith(".ovpn") or filename.endswith(".conf"):
                try:
                    # Extract the country code from the start of the file name (e.g., "US" from "US-FREE#...")
                    # This relies on ProtonVPN's consistent naming convention (e.g., US-FREE#2.conf)
                    country_code = filename.split('-')[0].split('#')[0].upper()
                    if len(country_code) > 2: # handle cases like "wg-CH" or "wg-US"
                        if country_code.startswith("WG-"):
                            country_code = country_code[3:]
                        else: # Fallback for complex names
                             country_code = filename.split('-')[0].upper()

                    if len(country_code) > 2 and country_code.isalpha():
                         # Assume 2-letter country code
                        country_code = country_code[:2]


                    if country_code not in country_files:
                        country_files[country_code] = []
                    
                    country_files[country_code].append(os.path.join(DOWNLOAD_DIR, filename))
                except Exception as e:
                    print(f"Error processing filename {filename}: {e}")

        if not country_files:
            print("No new configuration files found to organize/send.")
            return

        print(f"Found files for {len(country_files)} unique countries: {', '.join(country_files.keys())}")

        # 2. Zip and Send each country's files
        for country_code, files in country_files.items():
            zip_filename = f"{country_code}_ProtonVPN_Configs.zip"
            zip_path = os.path.join(os.getcwd(), zip_filename)
            
            # Create the zip file
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in files:
                    # Add file to zip with only the filename (not the full download path)
                    zipf.write(file_path, os.path.basename(file_path))

            print(f"Created {zip_filename} with {len(files)} configurations.")

            # 3. Send to Telegram
            if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
                caption = f"✅ کانفیگ‌های جدید WireGuard/OpenVPN برای کشور {country_code}."
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"

                try:
                    with open(zip_path, 'rb') as doc:
                        response = requests.post(url, 
                            data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}, 
                            files={'document': doc}
                        )
                    if response.status_code == 200:
                        print(f"Successfully sent {zip_filename} to Telegram.")
                    else:
                        print(f"Failed to send {zip_filename} to Telegram. Status code: {response.status_code}, Response: {response.text}")
                except Exception as e:
                    print(f"Telegram API Error for {zip_filename}: {e}")
            else:
                print("Skipping Telegram send: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured.")
            
            # 4. Clean up the created zip file
            os.remove(zip_path)
        
        print("File organization and sending process completed.")
        
        # 5. Clean up downloaded files (optional but recommended to prevent excessive CI space usage)
        print("Cleaning up individual configuration files...")
        for file in glob.glob(os.path.join(DOWNLOAD_DIR, '*')):
            os.remove(file)
        # Re-save the log file after cleanup (it should be empty now)
        self.save_downloaded_ids(set())


    def run(self, username, password):
        """Executes the full automation workflow with relogin cycle."""
        
        all_downloads_finished = False
        session_count = 0
        
        # Load previously downloaded IDs from the log file
        downloaded_ids = self.load_downloaded_ids()
        
        try:
            while not all_downloads_finished and session_count < 10: 
                
                session_count += 1
                print(f"\n###################### Starting Session {session_count} ######################")
                
                # 1. Setup Driver and Login
                self.setup()
                if not self.login(username, password):
                    print("Failed to log in. Aborting run.")
                    break
                
                # 2. Navigate and Download
                if self.navigate_to_downloads():
                    all_downloads_finished, downloaded_ids = self.process_downloads(downloaded_ids)
                    
                    # Save the current list of downloaded IDs after each session
                    self.save_downloaded_ids(downloaded_ids)
                
                # 3. Logout
                self.logout()
                self.teardown() 
                
                if all_downloads_finished:
                    print("\n###################### All configurations downloaded successfully! ######################")
                    # --- NEW: Organize and send files after all downloads are complete ---
                    self.organize_and_send_files()
                    # --------------------------------------------------------------------
                else:
                    print(f"Session {session_count} completed. Waiting {RELOGIN_DELAY} seconds before relogging in...")
                    time.sleep(RELOGIN_DELAY) 

        except Exception as e:
            print(f"Runtime Error in main loop: {e}")
        finally:
            self.teardown()


if __name__ == "__main__":
    USERNAME = os.environ.get("VPN_USERNAME")
    PASSWORD = os.environ.get("VPN_PASSWORD")
    
    if not USERNAME or not PASSWORD:
        print("---")
        print("ERROR: VPN_USERNAME or VPN_PASSWORD not loaded from environment variables.")
        print("Please configure them as Secrets in your GitHub repository.")
        print("---")
    else:
        print("Account info loaded from environment variables. Starting workflow...")
        proton = ProtonVPN()
        proton.run(USERNAME, PASSWORD)
