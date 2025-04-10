import requests
import io
import os
import mimetypes

import hashlib
import copy  # To avoid modifying the original new_data list when returning

from pathlib import Path
from typing import Any, Dict, List

from google.genai.types import File
from urllib.parse import urlparse
from google.genai import Client


def extract_post_data(data: Dict[str, str]):
    text = []
    img_links = []
    posts = data.get("posts", [])
    for post in posts:
        text.append(post.get("text", ""))
        img_links.append(post.get("img_links", []))
    return {"text": text, "img_links": img_links}


def upload_content_images(client: Client, imgs: List[str | Path]):
    images = []
    for img in imgs:
        image = client.files.upload(file=img)
        images.append(image)

    return images


def upload_images_from_urls(
    client: Client,  # Pass the initialized genai client
    image_urls: List[str],
) -> List[File]:
    """
    Downloads images from a list of URLs and uploads them to Gemini.

    Args:
        client: The initialized google.generativeai Client instance.
        image_urls: A list of strings, where each string is a URL pointing
                    to an image file.

    Returns:
        A list of google.generativeai.types.File objects representing the
        successfully uploaded files. Returns an empty list if no URLs
        are provided or if all uploads fail.

    Raises:
        requests.exceptions.RequestException: If a network error occurs during download.
        google.api_core.exceptions.GoogleAPIError: If the Gemini API upload fails.
        ValueError: If a URL is invalid or content cannot be retrieved.
    """
    uploaded_files = []
    if not image_urls:
        print("No image URLs provided.")
        return uploaded_files

    print(f"Attempting to upload {len(image_urls)} images...")

    for i, url in enumerate(image_urls):
        print(f"\nProcessing URL {i+1}/{len(image_urls)}: {url}")
        try:
            # 1. Download the image content
            print("  Downloading image...")
            response = requests.get(
                url, stream=True, timeout=30
            )  # stream=True is good practice
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            # Get content type from header if available
            content_type = response.headers.get("content-type")
            print(f"  Detected Content-Type: {content_type}")

            # Prepare a filename (try to extract from URL path)
            parsed_url = urlparse(url)
            # Get the last part of the path, remove query params etc.
            filename = os.path.basename(parsed_url.path)
            if not filename:  # Handle cases where path is just '/' or empty
                # Use a generic name if extraction fails
                filename = f"uploaded_image_{i+1}"
                # Try to guess extension from mime type if possible
                if content_type:
                    guessed_extension = mimetypes.guess_extension(content_type)
                    if guessed_extension:
                        filename += guessed_extension

            print(f"  Using filename: {filename}")

            # 2. Read content into memory
            image_bytes = (
                response.content
            )  # Reads the entire content if stream=True wasn't fully utilized elsewhere
            image_data = io.BytesIO(image_bytes)  # Wrap bytes in a file-like object

            # Ensure the stream is seekable (BytesIO is)
            if not image_data.seekable():
                raise ValueError(f"Downloaded data for {url} is not seekable.")
            image_data.seek(0)  # Reset stream position to the beginning

            # 3. Prepare upload configuration
            upload_config = {
                "display_name": filename,
                # Provide mime_type if known, otherwise let API infer (usually works)
                # If content_type is None, don't include mime_type in config
                **({"mime_type": content_type} if content_type else {}),
            }
            print(f"  Upload Config: {upload_config}")

            # 4. Upload using the SDK
            print("  Uploading to Gemini...")
            # Access the files service through the client instance
            uploaded_file = client.files.upload(
                file=image_data,  # Pass the BytesIO object
                config=upload_config,
            )
            uploaded_files.append(uploaded_file)
            print(
                f"  Successfully uploaded: {uploaded_file.name} (Display: {uploaded_file.display_name})"
            )

        except requests.exceptions.RequestException as e:
            print(f"  Error downloading {url}: {e}")
            # Optionally decide whether to continue or stop
            # continue

    print(f"\nFinished. Successfully uploaded {len(uploaded_files)} files.")
    return uploaded_files


def generate_post_hash(post):
    """
    Generates a SHA-256 hash for a post based on its text and sorted image links.

    Args:
        post (dict): A dictionary representing a single post,
                     expected to have 'text' and 'img_links' keys.

    Returns:
        str: A hexadecimal SHA-256 hash string representing the post content.
    """
    # Use .get() with defaults for robustness against missing keys
    text_content = post.get("text", "") or ""  # Ensure empty string if None
    img_links = sorted(post.get("img_links", []))  # Sort links for consistent order

    # Combine text and sorted image links into a single string
    # Using a separator to avoid potential ambiguities
    combined_content = f"text:{text_content}|||images:{'|'.join(img_links)}"

    # Create hash
    hasher = hashlib.sha256()
    hasher.update(combined_content.encode("utf-8"))  # Hash the UTF-8 encoded string
    return hasher.hexdigest()


def find_new_posts(old_data, new_data) -> List[Dict[str, Any]] | None:
    """
    Compares old and new scraped data to find posts present in new_data
    but not in old_data, based on content hashing.

    Args:
        old_data (dict): Dictionary loaded from the older JSON scrape result.
        new_data (dict): Dictionary loaded from the newer JSON scrape result.

    Returns:
        list: A list of post dictionaries from new_data that are considered new.
              Returns an empty list if no new posts are found or if input
              data is invalid.
    """
    if not isinstance(old_data, dict) or not isinstance(new_data, dict):
        print("Error: Input data must be dictionaries.")
        return None

    old_posts = old_data.get("posts", [])
    new_posts = new_data.get("posts", [])

    if not isinstance(old_posts, list) or not isinstance(new_posts, list):
        print("Error: Input data must contain a 'posts' list.")
        return None

    # 1. Generate hashes for all old posts and store them in a set for fast lookup
    old_post_hashes = set()
    for post in old_posts:
        if isinstance(post, dict):  # Ensure post is a dictionary
            post_hash = generate_post_hash(post)
            old_post_hashes.add(post_hash)
        else:
            print(f"Warning: Skipping invalid item in old_posts: {post}")

    # 2. Iterate through new posts, generate hash, and check against old hashes
    identified_new_posts = []
    for post in new_posts:
        if isinstance(post, dict):  # Ensure post is a dictionary
            current_hash = generate_post_hash(post)
            if current_hash not in old_post_hashes:
                # Make a copy to avoid modifying the original list if needed elsewhere
                identified_new_posts.append(copy.deepcopy(post))
        else:
            print(f"Warning: Skipping invalid item in new_posts: {post}")

    return identified_new_posts


# --- Example Usage ---

# Assume 'old_scrape.json' and 'new_scrape.json' contain your data
# Or load them from Supabase/wherever you store them

# Example using the provided data structure directly
old_scrape_data = {
    "url": "https://www.facebook.com/Batangas1ElectricCooperativeInc",
    "scraped_at": "2025-04-08T04:53:20.225142",  # Older time
    "posts": [
        {  # Post A (Same content as in new data)
            "text": "Alamin kung ano at kung bakit nagkakaroon ng ROTATIONAL BROWNOUT gayundin kung sino ang nag-aanunsyo ng mga maaapektuhang lugar nito. Sama-sama po nating puksain ang fake news at nawa\u2019y hindi tayo maging instrumento sa lalo pang pagpapakalat nito. \nPlease like and share!",
            "img_links": [
                "https://scontent.fmnl37-1.fna.fbcdn.net/v/t39.30808-6/489013393_1071257381695546_5153001472698797066_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=109&ccb=1-7&_nc_sid=127cfc&_nc_ohc=0CkCykRHaGUQ7kNvwGz5AUe&_nc_oc=Adl-DVc8voYjQj864Lx8lnNkniDVS1bfgZc2_r48u1HoMpgyLQIWMJi2kyk5Fnx2sPY&_nc_zt=23&_nc_ht=scontent.fmnl37-1.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfERiuleshZEjWeyTfIrDGFAW74iJlPK2uqK1iVwOH75mw&oe=67FA26C4",
                "https://scontent.fmnl3-3.fna.fbcdn.net/v/t39.30808-6/489145161_1071257375028880_4532715069200241563_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=111&ccb=1-7&_nc_sid=127cfc&_nc_ohc=O8XXqPUswaQQ7kNvwFrKeuK&_nc_oc=Adk-sUaTe1cU4tqfnWLNzo1QLSW9D2dg2Wh4ElDCk4CeW9pgzlImV9cYM2zoBSVoVTQ&_nc_zt=23&_nc_ht=scontent.fmnl3-3.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfEeGfR9h05H_2UobwhNoQ3EPN8ggKe699z-MVn9O-Fj9Q&oe=67FA1A88",
                "https://scontent.fmnl37-1.fna.fbcdn.net/v/t39.30808-6/490090270_1071257385028879_769340689318208477_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=106&ccb=1-7&_nc_sid=127cfc&_nc_ohc=GHc8tm6bn-0Q7kNvwGba4jC&_nc_oc=AdnomoYJ5-ZL-wTvTl7Yi5zhwcy2Lukdri2WAZTqB7i21pr7tynLT5tuaBmCOPxRcVA&_nc_zt=23&_nc_ht=scontent.fmnl37-1.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfFxdODvmC9OXOBVk1nqpZcUhn0JcY18P0fERhzjUeOOOg&oe=67FA07BD",
                "https://scontent.fmnl37-1.fna.fbcdn.net/v/t39.30808-6/489112152_1071257371695547_7684956009999510246_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=109&ccb=1-7&_nc_sid=127cfc&_nc_ohc=9RVAG3Uded0Q7kNvwFqZq2V&_nc_oc=AdkC7VFWzPmg8Bnv7gilJ3p1xcbeH1egoplOjzjmnraCTaCedZyRjz5-lWD7HdmtCsQ&_nc_zt=23&_nc_ht=scontent.fmnl37-1.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfHei7ntH0N-dIEeFI0ilo4SkZIVhwr9UpTuKUlD64gxGA&oe=67FA0151",
                "https://scontent.fmnl3-1.fna.fbcdn.net/v/t39.30808-6/489675821_1071257335028884_8091290143649607874_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=107&ccb=1-7&_nc_sid=127cfc&_nc_ohc=z7BH2vAZnH0Q7kNvwFwJzH9&_nc_oc=Adk3N1s_8jlMalgePlTzz2Tbm_3dy9_DYI62PbXHefI8na2GAoGwRkR9Njlo5MvhhDI&_nc_zt=23&_nc_ht=scontent.fmnl3-1.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfHNxSjNxNdmIxqAi6Kw-aJB-0Jd5EyvE9WBNIeo3WQpBg&oe=67FA288F",
            ],
            "timestamp": "1d",  # Older timestamp than in new data
        },
        {  # Post B (Does not exist in new data)
            "text": "This is an old post that got deleted or pushed out.",
            "img_links": [],
            "timestamp": "5d",
        },
        {  # Post C (Same as in new data)
            "text": "Happy Birthday, Dir. Edgardo Dimaano!",
            "img_links": [
                "https://scontent.fmnl37-2.fna.fbcdn.net/v/t39.30808-6/488249808_1067072072114077_4409766448063948065_n.jpg?stp=dst-jpg_p526x296_tt6&_nc_cat=108&ccb=1-7&_nc_sid=127cfc&_nc_ohc=wuxpEeSBCrcQ7kNvwFySnPz&_nc_oc=Adk2mkbpdrG0OnYExCfFy6vmDby1Px5_EGnF-sk0994quYdHE12TsAv3UN0lN-ei7PI&_nc_zt=23&_nc_ht=scontent.fmnl37-2.fna&_nc_gid=q9j4di0Ay9Wbr1pIkqzmog&oh=00_AfG-jnU7YnNWuOk6ECNpANwVkd2-30awO00D3BWGr2emog&oe=67F9F7EB"
            ],
            "timestamp": "3d",
        },
        # ... potentially more old posts
    ],
}

new_scrape_data = {
    "url": "https://www.facebook.com/Batangas1ElectricCooperativeInc",
    "scraped_at": "2025-04-09T05:00:00.000000",  # Newer time
    "posts": [
        {  # Post D (This is genuinely new)
            "text": "MAINTENANCE SCHEDULE | April 10, 2025\nPlease be advised...",
            "img_links": ["some_new_image_link.jpg"],
            "timestamp": "5m",
        },
        {  # Post A (Same content as in old data, different timestamp)
            "text": "Alamin kung ano at kung bakit nagkakaroon ng ROTATIONAL BROWNOUT gayundin kung sino ang nag-aanunsyo ng mga maaapektuhang lugar nito. Sama-sama po nating puksain ang fake news at nawa\u2019y hindi tayo maging instrumento sa lalo pang pagpapakalat nito. \nPlease like and share!",
            "img_links": [  # Links are the same, maybe in different order initially
                "https://scontent.fmnl37-1.fna.fbcdn.net/v/t39.30808-6/490090270_1071257385028879_769340689318208477_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=106&ccb=1-7&_nc_sid=127cfc&_nc_ohc=GHc8tm6bn-0Q7kNvwGba4jC&_nc_oc=AdnomoYJ5-ZL-wTvTl7Yi5zhwcy2Lukdri2WAZTqB7i21pr7tynLT5tuaBmCOPxRcVA&_nc_zt=23&_nc_ht=scontent.fmnl37-1.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfFxdODvmC9OXOBVk1nqpZcUhn0JcY18P0fERhzjUeOOOg&oe=67FA07BD",
                "https://scontent.fmnl3-3.fna.fbcdn.net/v/t39.30808-6/489145161_1071257375028880_4532715069200241563_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=111&ccb=1-7&_nc_sid=127cfc&_nc_ohc=O8XXqPUswaQQ7kNvwFrKeuK&_nc_oc=Adk-sUaTe1cU4tqfnWLNzo1QLSW9D2dg2Wh4ElDCk4CeW9pgzlImV9cYM2zoBSVoVTQ&_nc_zt=23&_nc_ht=scontent.fmnl3-3.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfEeGfR9h05H_2UobwhNoQ3EPN8ggKe699z-MVn9O-Fj9Q&oe=67FA1A88",
                "https://scontent.fmnl37-1.fna.fbcdn.net/v/t39.30808-6/489013393_1071257381695546_5153001472698797066_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=109&ccb=1-7&_nc_sid=127cfc&_nc_ohc=0CkCykRHaGUQ7kNvwGz5AUe&_nc_oc=Adl-DVc8voYjQj864Lx8lnNkniDVS1bfgZc2_r48u1HoMpgyLQIWMJi2kyk5Fnx2sPY&_nc_zt=23&_nc_ht=scontent.fmnl37-1.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfERiuleshZEjWeyTfIrDGFAW74iJlPK2uqK1iVwOH75mw&oe=67FA26C4",
                "https://scontent.fmnl3-1.fna.fbcdn.net/v/t39.30808-6/489675821_1071257335028884_8091290143649607874_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=107&ccb=1-7&_nc_sid=127cfc&_nc_ohc=z7BH2vAZnH0Q7kNvwFwJzH9&_nc_oc=Adk3N1s_8jlMalgePlTzz2Tbm_3dy9_DYI62PbXHefI8na2GAoGwRkR9Njlo5MvhhDI&_nc_zt=23&_nc_ht=scontent.fmnl3-1.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfHNxSjNxNdmIxqAi6Kw-aJB-0Jd5EyvE9WBNIeo3WQpBg&oe=67FA288F",
                "https://scontent.fmnl37-1.fna.fbcdn.net/v/t39.30808-6/489112152_1071257371695547_7684956009999510246_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=109&ccb=1-7&_nc_sid=127cfc&_nc_ohc=9RVAG3Uded0Q7kNvwFqZq2V&_nc_oc=AdkC7VFWzPmg8Bnv7gilJ3p1xcbeH1egoplOjzjmnraCTaCedZyRjz5-lWD7HdmtCsQ&_nc_zt=23&_nc_ht=scontent.fmnl37-1.fna&_nc_gid=eFHh-Z9n2h7mN8K09fkHjg&oh=00_AfHei7ntH0N-dIEeFI0ilo4SkZIVhwr9UpTuKUlD64gxGA&oe=67FA0151",
            ],
            "timestamp": "12h",  # Newer timestamp
        },
        {  # Post C (Same as in old data)
            "text": "Happy Birthday, Dir. Edgardo Dimaano!",
            "img_links": [
                "https://scontent.fmnl37-2.fna.fbcdn.net/v/t39.30808-6/488249808_1067072072114077_4409766448063948065_n.jpg?stp=dst-jpg_p526x296_tt6&_nc_cat=108&ccb=1-7&_nc_sid=127cfc&_nc_ohc=wuxpEeSBCrcQ7kNvwFySnPz&_nc_oc=Adk2mkbpdrG0OnYExCfFy6vmDby1Px5_EGnF-sk0994quYdHE12TsAv3UN0lN-ei7PI&_nc_zt=23&_nc_ht=scontent.fmnl37-2.fna&_nc_gid=q9j4di0Ay9Wbr1pIkqzmog&oh=00_AfG-jnU7YnNWuOk6ECNpANwVkd2-30awO00D3BWGr2emog&oe=67F9F7EB"
            ],
            "timestamp": "2d",
        },
        # ... other posts from your example new data will also be included here
        {
            "text": "Happiest Birthday po PRES\nwishing you all the BEST\nCHEERS & ENJOY",
            "img_links": [],
            "timestamp": "2d",
        },
        {
            "text": "* Mataas na Bayan Substation - Tamayo Feeder",
            "img_links": [
                "https://scontent.fmnl3-4.fna.fbcdn.net/v/t39.30808-6/489152205_1068889178599033_5822860129032481692_n.jpg?stp=dst-jpg_p526x296_tt6&_nc_cat=102&ccb=1-7&_nc_sid=833d8c&_nc_ohc=EfWoBfLC9KUQ7kNvwEznT0-&_nc_oc=AdmaBx7eJnhsPaR-i_syNJLkWIpqt49v-cTSfLnyYgHPV6jjzinKDRARPbf8QaIwIWY&_nc_zt=23&_nc_ht=scontent.fmnl3-4.fna&_nc_gid=q9j4di0Ay9Wbr1pIkqzmog&oh=00_AfElVHfMRR7oVtNtJUP9R2v7J2NXq_ZzLNQM9qZSpncwow&oe=67FA1329"
            ],
            "timestamp": "3d",
        },
        {
            "text": "Sama-sama po nating puksain ang fake news at nawa\u2019y hindi tayo maging instrumento sa lalo pang pagpapakalat nito. \nPlease like and share!",
            "img_links": [
                "https://scontent.fmnl37-1.fna.fbcdn.net/v/t39.30808-6/488239856_1067874702033814_3048448668038353465_n.jpg?stp=dst-jpg_p552x414_tt6&_nc_cat=109&ccb=1-7&_nc_sid=127cfc&_nc_ohc=gDAqW_-E_xIQ7kNvwEhiJ_A&_nc_oc=AdnK8zxiLt61mQNsBvCgGKlBPNl7HilI5ygEUnAZxu2pyf7mNPyBUJGynvzWVlyQIVc&_nc_zt=23&_nc_ht=scontent.fmnl37-1.fna&_nc_gid=q9j4di0Ay9Wbr1pIkqzmog&oh=00_AfHnDiyuN0uz66iaTY_SGgDa8-xnfZp761Tqep0o0iFG5w&oe=67FA009E"
            ],
            "timestamp": "4d",
        },
        {"text": "Michael M. Arellano hahahahahha", "img_links": [], "timestamp": "3d"},
        {
            "text": "IN PHOTOS | This program aims to address the challenges with energy consumption and supply through its Quantum and Intelligent Systems Laboratory for Power Engineering (QISLaP) located at TIP\u2019s campus in Manila.  \nThis quantum laboratory, the first in the country to focus on energy supply issues, is funded by the Department of Science and Technology \u2013 Philippine Council for Industry, Energy, and Emerging Technology Research and Development (DOST-PCIEERD).\nDuring the Grand Ceremonial Signing of the MOU and the inauguration of the Quantum laboratory on March 21, 2025, BATELEC I was presented with the following areas of cooperation:\n\u2022 Provide essential project data;\n\u2022 Participate in training sessions;\n\u2022 Provide an actual environment for the deployment of the Quantum AI Models;\n\u2022 Evaluate the performance of the Quantum AI models; and \n\u2022 Help in drafting a position paper on hybrid Quantum Computing in Energy.\nAside from BATELEC I, TIP\u2019s partners on this project include DOST-PCIEERD, Department of Energy, DOST\u2013Niche Centers in the Regions (NICER) Science for Change Program, and Philippine Batteries, Inc. (PBI).",
            "img_links": [
                "https://scontent.fmnl3-1.fna.fbcdn.net/v/t39.30808-6/488257976_1067761278711823_1544773291386083809_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=110&ccb=1-7&_nc_sid=127cfc&_nc_ohc=76QVVA-O8vAQ7kNvwE7ebyz&_nc_oc=Adna12pJe8XjZeeISQNg1-zssdMjeeFYwF4AN3IhiNOOwyepBfYgNkoibB5BEd8bOss&_nc_zt=23&_nc_ht=scontent.fmnl3-1.fna&_nc_gid=pH_awJ_ZqTqCe2z6eLPQmw&oh=00_AfGxh0pU9GIH0aOSKquWIvK4H9wigTbl7PamvIejAySf6Q&oe=67FA0B86",
                "https://scontent.fmnl37-1.fna.fbcdn.net/v/t39.30808-6/488166105_1067761282045156_871764544480500320_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=109&ccb=1-7&_nc_sid=127cfc&_nc_ohc=4cq8At78Y4oQ7kNvwHW-3lU&_nc_oc=Adl5cR1LqEZdRHI8jp9OWhTS9WmqPHF9gK-CUeG1br-rsk7jv47p1hPjbxazcnKkgss&_nc_zt=23&_nc_ht=scontent.fmnl37-1.fna&_nc_gid=pH_awJ_ZqTqCe2z6eLPQmw&oh=00_AfFc18ffLWUtvpCV2i5ubhKkBpLyNHECP4yV_GU5S6hLTA&oe=67FA19F8",
                "https://scontent.fmnl37-1.fna.fbcdn.net/v/t39.30808-6/487806992_1067761275378490_3536050453747515548_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=109&ccb=1-7&_nc_sid=127cfc&_nc_ohc=kmwOmEm0QcAQ7kNvwEE69IC&_nc_oc=AdnesqUYDit_GAlE4Za8uZTymGtkOE2shWUNvPfAhSpGtiZcAJcjI-cDCLoFKZ9FiP8&_nc_zt=23&_nc_ht=scontent.fmnl37-1.fna&_nc_gid=pH_awJ_ZqTqCe2z6eLPQmw&oh=00_AfEhaC7UMScrcl_Qkyq_hV0490XcQVzfryuqYVwyL94zmw&oe=67FA128F",
                "https://scontent.fmnl3-4.fna.fbcdn.net/v/t39.30808-6/487876715_1067767885377829_3488869964775432588_n.jpg?stp=dst-jpg_p526x395_tt6&_nc_cat=101&ccb=1-7&_nc_sid=127cfc&_nc_ohc=ZWcHJgKKgNQQ7kNvwHL7VE5&_nc_oc=AdkAUV-xZAToLNL9Uy8um6bmoczHMotykLVTBOSJjSHKLSzL6k6mSPniJAvyzbE629k&_nc_zt=23&_nc_ht=scontent.fmnl3-4.fna&_nc_gid=pH_awJ_ZqTqCe2z6eLPQmw&oh=00_AfFBBpz5gqavSaTrI35TV-tzgpsLmcg4M-lxsrHo9g9JRw&oe=67FA0639",
                "https://scontent.fmnl3-4.fna.fbcdn.net/v/t39.30808-6/488252134_1067767898711161_2418644527536328478_n.jpg?stp=dst-jpg_s600x600_tt6&_nc_cat=101&ccb=1-7&_nc_sid=127cfc&_nc_ohc=joMug5IewpkQ7kNvwEchPN1&_nc_oc=AdkQSzTt4-MCfGdgtUkH7rx5xEjIGHdksk-gdw4pxJIkso1niGZM60ugIeKjhjkeIQc&_nc_zt=23&_nc_ht=scontent.fmnl3-4.fna&_nc_gid=pH_awJ_ZqTqCe2z6eLPQmw&oh=00_AfGrrqeliTt7SruXeyEXHuRFo9l9B-er1_1ilxLJLFNBLQ&oe=67FA2497",
            ],
            "timestamp": "4d",
        },
        {
            "text": "hello po bka pwde nyo po maaksuyanan ang kurynte dto smin sa biga centro calatagan ang kuryente po eh 160voltage lng po ang pasok sa bawat bhay kay sira ang aming mga appliances po imbis n 210 po ang dpat n voltage n napasok bka pwde nyo aksyunan agad at ngbbyad nman kme ng maayos sa kurynte po need po sguro ng transformer hlos 25kme pmilya nag susuffer ng gnito.",
            "img_links": [],
            "timestamp": "14h",
        },
    ],
}
