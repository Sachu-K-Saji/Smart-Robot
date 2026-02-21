# Complete Beginner's Guide to Web Crawling — Zero Experience Required

This guide assumes you have never written a single line of code. Every step is explained in full detail, including what things mean and why you're doing them.

---

## Part 1: Understanding What's Happening (Read This First)

Before touching your keyboard, let's understand what we're actually doing.

**What is a website made of?**
Every webpage you visit is just a text file written in a language called HTML. When you open a browser and go to a website, your browser downloads that text file and turns it into the visual page you see. A crawler is a program that automatically downloads those text files one by one — across hundreds or thousands of pages — and pulls out the information you want.

**What is Python?**
Python is a programming language — essentially a set of instructions your computer can understand. It reads like plain English, which makes it the best choice for beginners. When you write a Python script, you're writing a recipe of instructions, and Python executes them one by one.

**What are libraries?**
Libraries are pre-written collections of code that other programmers have already built and shared for free. Instead of building everything yourself, you install a library and use its tools. For crawling, we'll use libraries called `requests` (to download web pages) and `BeautifulSoup` (to read and extract content from them).

---

## Part 2: Setting Up Your Computer

### Step 1 — Install Python

Python does not come pre-installed on most computers. You need to download and install it first.

**On Windows:**

1. Open your browser and go to `https://www.python.org/downloads/`
2. You will see a big yellow button that says **"Download Python 3.x.x"** — click it. The x's will be a version number like 3.12.2, it doesn't matter exactly which version.
3. Once the file downloads, open it by double-clicking it. An installer window will appear.
4. **Very important:** Before clicking anything, look at the bottom of that window. There is a checkbox that says **"Add Python to PATH"**. Make sure that box is ticked/checked. If you skip this, nothing will work.
5. Click **"Install Now"** and wait for it to finish.
6. Click **Close** when done.

**On Mac:**

1. Go to `https://www.python.org/downloads/`
2. Click the download button and open the `.pkg` file that downloads.
3. Follow the on-screen instructions, clicking Continue and Agree when prompted.
4. Click Install and enter your Mac password if asked.

**Verify it worked:**

On Windows, press the **Windows key**, type `cmd`, and press Enter. A black window called the Command Prompt will open.

On Mac, press **Cmd + Space**, type `terminal`, and press Enter. A window will open.

In that window, type exactly this and press Enter:

```
python --version
```

You should see something like `Python 3.12.2`. If you do, Python is installed correctly. If you see an error, try typing `python3 --version` instead, which works on some Macs.

---

### Step 2 — Understand the Terminal / Command Prompt

The black window you just opened — called the **Terminal** on Mac or **Command Prompt** on Windows — is where you will run your programs. You type commands here and press Enter to execute them. It looks intimidating but you'll only ever use a handful of commands.

Here are the ones you need to know:

`cd` means "change directory" — it's how you move into a folder. For example, `cd Desktop` takes you into your Desktop folder.

`ls` (Mac) or `dir` (Windows) lists all files in your current folder so you can see where you are.

`python filename.py` runs a Python script called `filename.py`.

You'll use these throughout this guide.

---

### Step 3 — Install a Code Editor

You write Python code in a text editor designed for code. The best free one for beginners is **Visual Studio Code (VS Code)**.

1. Go to `https://code.visualstudio.com/`
2. Click the big download button for your operating system.
3. Open the downloaded file and follow the installation steps, clicking Next/Agree throughout.
4. Open VS Code once installed. You'll see a welcome screen.

---

### Step 4 — Create a Project Folder

You need a dedicated folder where all your crawling files will live.

1. Go to your Desktop (or Documents — wherever you prefer).
2. Right-click on an empty area and choose **New Folder**.
3. Name it something like `my_crawler`.

Now open VS Code, go to **File → Open Folder**, and select the `my_crawler` folder you just created. VS Code will now show that folder in its left panel.

---

### Step 5 — Install the Required Libraries

Libraries are installed using a tool called `pip`, which comes bundled with Python. You install them through the Terminal.

Open your Terminal or Command Prompt and type each of these lines one at a time, pressing Enter after each one and waiting for it to finish before typing the next:

```
pip install requests
```

```
pip install beautifulsoup4
```

```
pip install lxml
```

You will see a lot of text scrolling by — that's normal. It means things are downloading and installing. When it stops and you see your cursor blinking again, it's done.

If `pip` doesn't work, try `pip3` instead (common on Mac).

---

## Part 3: Writing Your First Crawler

### Step 6 — Create Your Script File

In VS Code, look at the left panel where your `my_crawler` folder is shown. Right-click on the folder name and choose **New File**. Name it `crawler.py`. The `.py` extension tells your computer it's a Python file.

You should now see a blank white area in the centre of VS Code — this is where you write code.

---

### Step 7 — Understanding the Code Before You Write It

Here is the full script you'll be writing. Read the explanation below each section before copying anything.

**Section 1 — Imports**

```python
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import time
```

This section loads the libraries you installed. Think of it like pulling tools out of a toolbox before starting a job. `requests` lets you download web pages. `BeautifulSoup` lets you read and search through the HTML of those pages. `urljoin` and `urlparse` help you handle web addresses (URLs) correctly. `json` lets you save your data in a structured file. `time` lets you add pauses between requests so you don't overload the website's server.

**Section 2 — Configuration**

```python
START_URL = "https://example.com"   # The website you want to crawl
MAX_PAGES = 20                        # How many pages to crawl before stopping
OUTPUT_FILE = "results.json"          # Name of the file your data will be saved in
DELAY_SECONDS = 1.5                   # Seconds to wait between each page request
```

These are the settings you'll change to point the crawler at different websites. You only need to edit these lines — everything else stays the same.

**Section 3 — Setup**

```python
visited_urls = set()       # A collection of URLs we've already crawled (so we don't repeat)
urls_to_visit = [START_URL]  # A queue of URLs we still need to crawl
all_data = []              # A list where we'll store all the data we extract
```

Think of `visited_urls` like a notebook where you write down every page you've been to, so you don't accidentally visit the same page twice. `urls_to_visit` is your to-do list of pages waiting to be crawled. `all_data` is the bucket where you collect everything.

**Section 4 — The Main Crawling Loop**

This is where the actual work happens. The crawler will keep going until either the to-do list is empty or you've hit your maximum page limit.

```python
while urls_to_visit and len(visited_urls) < MAX_PAGES:
    current_url = urls_to_visit.pop(0)

    if current_url in visited_urls:
        continue

    print(f"Crawling page {len(visited_urls) + 1}: {current_url}")
```

`while` means "keep doing this as long as the condition is true." `urls_to_visit.pop(0)` takes the first URL off the to-do list. The `if` check skips any URL we've already visited. `print` shows you what's happening in real time so you can follow along.

**Section 5 — Downloading and Reading the Page**

```python
    try:
        response = requests.get(current_url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; LearnerBot/1.0)"
        })
        response.raise_for_status()
    except Exception as error:
        print(f"   Could not load this page: {error}")
        continue
```

`requests.get()` downloads the web page at the given URL, just like your browser would. The `timeout=10` means if the page takes more than 10 seconds to respond, skip it and move on. The `User-Agent` is a label that tells the website what kind of program is visiting — here we're identifying ourselves as a bot. `try/except` is error handling: if anything goes wrong (the page doesn't exist, the internet drops out, etc.) we catch the error, print a message, and move on instead of crashing the whole program.

**Section 6 — Extracting Data**

```python
    soup = BeautifulSoup(response.text, "lxml")

    page_data = {
        "url": current_url,
        "page_title": soup.title.get_text(strip=True) if soup.title else "No title",
        "headings": [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"])],
        "paragraphs": [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)],
        "all_links": [a["href"] for a in soup.find_all("a", href=True)],
        "image_sources": [img["src"] for img in soup.find_all("img", src=True)],
    }

    all_data.append(page_data)
    visited_urls.add(current_url)
```

`BeautifulSoup(response.text, "lxml")` takes the raw HTML text of the page and turns it into a structured object you can search through. Think of it like a searchable map of the page. `soup.title.get_text()` finds the page title. `soup.find_all("p")` finds every paragraph. The square bracket syntax like `[p.get_text() for p in soup.find_all("p")]` is a compact loop that says "for every paragraph found, get its text and put it in a list."

**Section 7 — Discovering New Links**

```python
    base_domain = urlparse(START_URL).netloc

    for link_tag in soup.find_all("a", href=True):
        absolute_url = urljoin(current_url, link_tag["href"])
        absolute_url = absolute_url.split("#")[0]

        if urlparse(absolute_url).netloc == base_domain:
            if absolute_url not in visited_urls and absolute_url not in urls_to_visit:
                urls_to_visit.append(absolute_url)

    time.sleep(DELAY_SECONDS)
```

After extracting data, we look for all the links on that page and add them to our to-do list. `urljoin` converts relative links like `/about` into full addresses like `https://example.com/about`. The `.split("#")[0]` removes anchor fragments (like `#section2`) from URLs since they don't point to new pages. The `netloc` check ensures we only follow links that stay on the same website — we don't want to accidentally start crawling the entire internet. `time.sleep()` pauses for the number of seconds you set, being polite to the server.

**Section 8 — Saving the Results**

```python
print(f"\nFinished! Crawled {len(visited_urls)} pages.")

with open(OUTPUT_FILE, "w", encoding="utf-8") as output_file:
    json.dump(all_data, output_file, indent=2, ensure_ascii=False)

print(f"Data saved to {OUTPUT_FILE}")
```

`json.dump()` takes all the data you collected and writes it into a `.json` file — a structured text format that can be opened in any text editor, imported into Excel, or used in other programs. `indent=2` makes the file nicely formatted and human-readable.

---

### Step 8 — The Complete Script (Copy This Into VS Code)

Now that you understand each section, here is the full script. Copy all of it into your `crawler.py` file in VS Code:

```python
# =============================================
# Simple Web Crawler for Beginners
# =============================================

# Step 1: Load the tools we need
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import json
import time

# =============================================
# SETTINGS — Edit these to change the crawler
# =============================================
START_URL = "https://books.toscrape.com"  # Safe practice site, no login needed
MAX_PAGES = 20
OUTPUT_FILE = "results.json"
DELAY_SECONDS = 1.5

# =============================================
# Internal tracking variables
# =============================================
visited_urls = set()
urls_to_visit = [START_URL]
all_data = []

base_domain = urlparse(START_URL).netloc

# =============================================
# Main crawling loop
# =============================================
print(f"Starting crawl on: {START_URL}")
print(f"Will crawl up to {MAX_PAGES} pages.\n")

while urls_to_visit and len(visited_urls) < MAX_PAGES:

    current_url = urls_to_visit.pop(0)

    if current_url in visited_urls:
        continue

    print(f"Crawling page {len(visited_urls) + 1} of {MAX_PAGES}: {current_url}")

    # Download the page
    try:
        response = requests.get(current_url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; LearnerBot/1.0)"
        })
        response.raise_for_status()
    except Exception as error:
        print(f"   Could not load: {error}")
        continue

    # Parse the HTML
    soup = BeautifulSoup(response.text, "lxml")

    # Extract data from the page
    page_data = {
        "url": current_url,
        "page_title": soup.title.get_text(strip=True) if soup.title else "No title found",
        "headings": [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"])],
        "paragraphs": [p.get_text(strip=True) for p in soup.find_all("p") if p.get_text(strip=True)],
        "all_links_on_page": [a["href"] for a in soup.find_all("a", href=True)],
        "image_sources": [img["src"] for img in soup.find_all("img", src=True)],
    }

    all_data.append(page_data)
    visited_urls.add(current_url)

    # Find new links to add to the queue
    for link_tag in soup.find_all("a", href=True):
        absolute_url = urljoin(current_url, link_tag["href"])
        absolute_url = absolute_url.split("#")[0]

        if urlparse(absolute_url).netloc == base_domain:
            if absolute_url not in visited_urls and absolute_url not in urls_to_visit:
                urls_to_visit.append(absolute_url)

    # Wait politely before the next request
    time.sleep(DELAY_SECONDS)

# =============================================
# Save everything to a file
# =============================================
print(f"\nDone! Crawled {len(visited_urls)} pages.")

with open(OUTPUT_FILE, "w", encoding="utf-8") as output_file:
    json.dump(all_data, output_file, indent=2, ensure_ascii=False)

print(f"All data saved to: {OUTPUT_FILE}")
```

Notice the `START_URL` is set to `https://books.toscrape.com` — this is a website specifically built for people learning to crawl. It's completely legal and safe to practice on and won't block you.

---

## Part 4: Running the Crawler

### Step 9 — Open the Terminal Inside VS Code

In VS Code, go to the menu bar at the top and click **Terminal → New Terminal**. A small black panel will appear at the bottom of VS Code. This is your terminal, and it's already pointed at your `my_crawler` folder automatically — which is perfect.

---

### Step 10 — Run the Script

In that terminal panel, type:

```
python crawler.py
```

And press Enter.

You will immediately start seeing output like this:

```
Starting crawl on: https://books.toscrape.com
Will crawl up to 20 pages.

Crawling page 1 of 20: https://books.toscrape.com
Crawling page 2 of 20: https://books.toscrape.com/catalogue/page-2.html
Crawling page 3 of 20: https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html
...
Done! Crawled 20 pages.
All data saved to: results.json
```

The terminal is printing each page as it crawls it. When it finishes, look in your `my_crawler` folder in the VS Code left panel — you'll see a new file called `results.json` has appeared.

---

### Step 11 — View Your Results

Click on `results.json` in the VS Code left panel to open it. You'll see structured data that looks like this:

```json
[
  {
    "url": "https://books.toscrape.com",
    "page_title": "All products | Books to Scrape - Sandbox",
    "headings": [
      "Books to Scrape",
      "All products"
    ],
    "paragraphs": [
      "Warning! This is a fictional bookstore...",
      "1000 results - showing 1 to 20."
    ],
    "all_links_on_page": [
      "/",
      "catalogue/page-2.html",
      ...
    ],
    "image_sources": [
      "media/cache/2c/da/2cdad67c44b002e7ead0cc35693c0e8b.jpg",
      ...
    ]
  },
  {
    "url": "https://books.toscrape.com/catalogue/page-2.html",
    ...
  }
]
```

Each page's data is stored as one block, and all the blocks are collected in a list. This file can be imported into Excel, Google Sheets, databases, or processed further with code.

---

## Part 5: Customising the Crawler for Your Needs

### Changing the target website

Simply change the `START_URL` line:

```python
START_URL = "https://yourwebsite.com"
```

Make sure you have permission to crawl the site first. Always check `https://yourwebsite.com/robots.txt` — this file lists what crawlers are and aren't allowed to access.

### Crawling more or fewer pages

Change `MAX_PAGES`:

```python
MAX_PAGES = 100   # Crawl up to 100 pages
```

### Changing what data you extract

Inside the `page_data` dictionary, you can add or remove fields. For example, if you want to also extract the date an article was published, you'd first inspect the page in your browser (right-click → Inspect) to find what HTML tag holds the date, then add a line like:

```python
"publish_date": soup.find("time").get_text(strip=True) if soup.find("time") else "Not found",
```

---

## Part 6: Common Errors and How to Fix Them

**"ModuleNotFoundError: No module named 'requests'"**
This means the library didn't install properly. Run `pip install requests` in the terminal again.

**"python is not recognized as a command"**
Python was installed without being added to PATH. Uninstall Python and re-install it, making sure to tick the "Add Python to PATH" checkbox this time.

**"ConnectionError" or "Timeout"**
The website is either blocking you or is temporarily unavailable. Try increasing `DELAY_SECONDS` to 3 or 5 and try again.

**The results.json file is empty or has no data**
The website likely uses JavaScript to load its content, which means the basic `requests` library can't see the content. You would need to use Playwright instead, which is a more advanced tool that runs a real browser — let me know if you reach this point and need guidance on that.

---

## Part 7: Important Rules to Follow

**Always check robots.txt.** Go to the website you want to crawl and add `/robots.txt` to the address. For example: `https://example.com/robots.txt`. This file tells you what automated tools are and aren't allowed to access. Respect what it says.

**Never crawl without permission on private or sensitive sites.** Crawling certain sites without permission can violate their terms of service or even laws in some countries. Stick to public data and sites that explicitly allow it, or sites you own.

**Don't remove the delay.** Setting `DELAY_SECONDS` to 0 will bombard the server with requests and could crash it or get your IP address permanently banned. The delay is not optional — it's basic courtesy.

**Don't share or sell scraped data without checking the site's terms.** Even if crawling is allowed, how you use the data may be restricted.

---

You now have a fully working web crawler built from scratch. Every concept has been explained from the ground up, and you can start experimenting with it immediately on the practice site. Once you're comfortable, try pointing it at a website you have permission to crawl and adjusting the extraction fields to pull exactly the data you need.
