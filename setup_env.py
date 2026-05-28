import os
import sys
import subprocess
import time
import urllib.request
import socket
import json

# Set global timeout of 90 seconds to prevent urllib calls hanging indefinitely on flaky connections
socket.setdefaulttimeout(90.0)

WORKSPACE = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = os.path.join(WORKSPACE, "tmp")
os.makedirs(TMP_DIR, exist_ok=True)

PIP_REQUIREMENTS = [
    "pyyaml",
    "requests",
    "pyautogui",
    "easyocr",
    "opencv-python",
    "sounddevice",
    "soundfile",
    "vosk",
    "faster-whisper",
    "pyttsx3",
    "playwright",
    "numpy",
    "keyboard",
    "python-telegram-bot",
    "transformers==4.49.0",
    "huggingface_hub",
    "pillow",
    "beautifulsoup4",
    "psutil",
    "einops",
    "timm",
]

OLLAMA_MODELS = [
    "llama3.2:1b",
    "qwen2.5:7b-instruct",
    "deepseek-r1:7b",
    "nomic-embed-text",
    "qwen2.5-coder:7b"
]

def print_banner(text):
    print("\n" + "=" * 50)
    print(f" {text}")
    print("=" * 50)

def run_command(args, shell=False):
    print(f"Running: {' '.join(args) if isinstance(args, list) else args}")
    try:
        result = subprocess.run(args, shell=shell, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        print(f"Stderr: {e.stderr}")
        return None

def is_ollama_running():
    try:
        with socket.create_connection(("localhost", 11434), timeout=2):
            return True
    except OSError:
        return False

def check_or_install_pip():
    print_banner("Checking & Installing Python Dependencies")
    # Check PyTorch first for GPU support
    try:
        import torch
        print(f"PyTorch already installed. CUDA Available: {torch.cuda.is_available()}")
    except ImportError:
        print("Installing PyTorch with CUDA support...")
        # Target CUDA 12.1 for modern GPUs
        run_command([sys.executable, "-m", "pip", "install", "torch", "torchvision", "torchaudio", "--index-url", "https://download.pytorch.org/whl/cu121"])

    # Import name mappings for package checks
    import_mapping = {
        "beautifulsoup4": "bs4",
        "python-telegram-bot": "telegram",
        "faster-whisper": "faster_whisper",
        "transformers==4.49.0": "transformers",
    }
    
    # Install other requirements
    for req in PIP_REQUIREMENTS:
        import_name = import_mapping.get(req, req.replace("-", "_"))
        try:
            __import__(import_name)
            print(f"Package '{req}' is already installed.")
        except ImportError:
            print(f"Installing package '{req}'...")
            run_command([sys.executable, "-m", "pip", "install", req])

    # Install Playwright browser
    print("Installing Playwright Chromium browser...")
    run_command([sys.executable, "-m", "playwright", "install", "chromium"])

def check_or_install_ollama():
    print_banner("Checking Ollama Installation")
    
    # Check if 'ollama' exists in system PATH
    ollama_path_check = run_command(["where", "ollama"], shell=True)
    
    if not ollama_path_check:
        print("Ollama was not found in the system PATH. Initiating download...")
        installer_path = os.path.join(TMP_DIR, "OllamaSetup.exe")
        url = "https://ollama.com/download/OllamaSetup.exe"
        
        print(f"Downloading Ollama installer from {url}...")
        try:
            # Try native curl.exe first for download robustness, redirect handling, and timeouts
            try:
                print("Using native curl.exe for download...")
                subprocess.run(["curl.exe", "-L", "-o", installer_path, url], check=True)
                print("Download completed successfully via curl.")
            except (subprocess.SubprocessError, FileNotFoundError):
                print("curl.exe failed or not found. Falling back to urllib...")
                urllib.request.urlretrieve(url, installer_path)
                print("Download completed successfully via urllib.")
        except Exception as e:
            print(f"Failed to download Ollama: {e}")
            print(f"Please manually download and install Ollama from: {url}")
            return False
        
        print("Running Ollama installer silently...")
        try:
            # Install silently
            subprocess.run([installer_path, "/S"], check=True)
            print("Ollama installation triggered successfully.")
            # Wait for Ollama to finish setup and add to environment
            print("Waiting for Ollama files to settle...")
            time.sleep(10)
        except Exception as e:
            print(f"Silent installation failed: {e}")
            print(f"Please install Ollama manually using the downloaded file: {installer_path}")
            return False

    # Start Ollama service if not running
    if not is_ollama_running():
        print("Starting Ollama background process...")
        try:
            # Start Ollama application in the background
            if os.name == 'nt':
                # Windows specific launch
                local_app_data = os.environ.get("LOCALAPPDATA", "")
                ollama_app_path = os.path.join(local_app_data, "Programs", "Ollama", "ollama app.exe")
                if os.path.exists(ollama_app_path):
                    subprocess.Popen([ollama_app_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(["ollama", "serve"], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Wait for it to spin up
            for i in range(10):
                if is_ollama_running():
                    print("Ollama is now running.")
                    break
                print("Waiting for Ollama to start...")
                time.sleep(2)
        except Exception as e:
            print(f"Could not automatically start Ollama: {e}")

    # Double check running state
    if is_ollama_running():
        print("Ollama is verified running on http://localhost:11434")
        return True
    else:
        print("Ollama is not running. Please start Ollama manually from the system tray or command prompt.")
        return False

def pull_ollama_models():
    if not is_ollama_running():
        print("Skipping model pulling because Ollama is not running.")
        return

    print_banner("Pulling Ollama Models")
    for model in OLLAMA_MODELS:
        print(f"\nChecking model availability: {model}...")
        # Check if model exists
        url = f"http://localhost:11434/api/show"
        req = urllib.request.Request(url, data=json.dumps({"name": model}).encode('utf-8'), headers={'Content-Type': 'application/json'})
        
        exists = False
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    exists = True
                    print(f"Model '{model}' is already available locally.")
        except Exception:
            pass

        if not exists:
            print(f"Pulling model: {model} (this may take several minutes)...")
            try:
                # Use subprocess to run the CLI pull which handles progress output and connection state
                subprocess.run(["ollama", "pull", model], check=True)
                print(f"Completed pulling model '{model}'.")
            except Exception as e:
                print(f"Failed to pull model '{model}' automatically: {e}")
                print(f"Please pull manually via terminal: ollama pull {model}")

def main():
    print_banner("Jarvis Environment Setup Script")
    check_or_install_pip()
    ollama_ok = check_or_install_ollama()
    if ollama_ok:
        pull_ollama_models()
    print_banner("Setup Verification Completed")

if __name__ == "__main__":
    main()
