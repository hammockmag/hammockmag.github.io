#!/usr/bin/env python3
"""
Migrate URLs in data.geojson from old sitemap structure to new.

Old: www.hammockmag.com/recommendations-lists/<slug>  (and other category prefixes)
New: hammockmag.com/<slug>  (flat structure, some slugs changed)

Matching strategy:
1. Exact slug match (slug unchanged, just prefix removed)
2. Fuzzy match on slug (for slugs that changed during migration)
"""

import xml.etree.ElementTree as ET
import json
from urllib.parse import urlparse
from difflib import SequenceMatcher

SITEMAP_OLD = "sitemap-old.xml"
SITEMAP_NEW = "sitemap-new.xml"
GEOJSON = "data.geojson"
GEOJSON_OUT = "data.geojson"  # overwrite in place


def parse_sitemap(path):
    """Extract all URLs from a sitemap XML file."""
    tree = ET.parse(path)
    root = tree.getroot()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = []
    for loc in root.findall(".//sm:loc", ns):
        urls.append(loc.text.strip())
    return urls


def get_slug(url):
    """Extract the final path segment (slug) from a URL."""
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1] if path else ""


def build_url_mapping(old_urls, new_urls):
    """
    Build a mapping from old URL -> new URL.

    Pass 1: exact slug match
    Pass 2: fuzzy match for remaining unmatched URLs (threshold: 0.6)
    """
    # Index new URLs by slug for fast lookup
    new_by_slug = {}
    for url in new_urls:
        slug = get_slug(url)
        if slug:
            new_by_slug.setdefault(slug, []).append(url)

    mapping = {}
    unmatched_old = []

    # Pass 1: exact slug match
    for old_url in old_urls:
        old_slug = get_slug(old_url)
        if not old_slug:
            continue
        if old_slug in new_by_slug:
            mapping[old_url] = new_by_slug[old_slug][0]
        else:
            unmatched_old.append(old_url)

    # Pass 2: fuzzy match for remaining
    used_new = set(mapping.values())
    available_new = [(url, get_slug(url)) for url in new_urls if url not in used_new]

    for old_url in unmatched_old:
        old_slug = get_slug(old_url)
        best_score = 0
        best_match = None
        for new_url, new_slug in available_new:
            score = SequenceMatcher(None, old_slug, new_slug).ratio()
            if score > best_score:
                best_score = score
                best_match = new_url
        if best_score >= 0.6:
            mapping[old_url] = best_match
            available_new = [(u, s) for u, s in available_new if u != best_match]

    return mapping


def normalize_old_url(url):
    """Normalize www./non-www and trailing slashes for comparison."""
    return url.replace("https://www.", "https://").rstrip("/")


def main():
    print("Parsing sitemaps...")
    old_urls = parse_sitemap(SITEMAP_OLD)
    new_urls = parse_sitemap(SITEMAP_NEW)
    print(f"  Old sitemap: {len(old_urls)} URLs")
    print(f"  New sitemap: {len(new_urls)} URLs")

    print("\nBuilding URL mapping...")
    mapping = build_url_mapping(old_urls, new_urls)
    print(f"  Mapped: {len(mapping)} URLs")

    # Also build a normalized lookup (handles www vs non-www)
    normalized_mapping = {}
    for old, new in mapping.items():
        normalized_mapping[normalize_old_url(old)] = new

    # Print the mapping for review
    print("\n--- URL Mapping ---")
    for old, new in sorted(mapping.items()):
        old_slug = get_slug(old)
        new_slug = get_slug(new)
        changed = " (slug changed)" if old_slug != new_slug else ""
        print(f"  {old}")
        print(f"    -> {new}{changed}")

    # Find unmatched old URLs (excluding category/author/structural pages)
    unmatched = [u for u in old_urls if u not in mapping and get_slug(u)]
    if unmatched:
        print(f"\n--- Unmatched Old URLs ({len(unmatched)}) ---")
        for u in unmatched:
            print(f"  {u}")

    # Update geojson
    print(f"\nUpdating {GEOJSON}...")
    with open(GEOJSON, "r") as f:
        data = json.load(f)

    updated_count = 0
    not_found = []
    for feature in data["features"]:
        props = feature["properties"]
        list_url = props.get("list_url", "")
        if not list_url:
            continue

        norm = normalize_old_url(list_url)
        if norm in normalized_mapping:
            new_url = normalized_mapping[norm]
            if list_url != new_url:
                props["list_url"] = new_url
                updated_count += 1
        else:
            not_found.append(list_url)

    print(f"  Updated: {updated_count} URLs in data.geojson")

    if not_found:
        unique_not_found = sorted(set(not_found))
        print(f"\n--- URLs in geojson not found in mapping ({len(unique_not_found)}) ---")
        for u in unique_not_found:
            print(f"  {u}")

    # Write output
    with open(GEOJSON_OUT, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"\nDone. Written to {GEOJSON_OUT}")


if __name__ == "__main__":
    main()
