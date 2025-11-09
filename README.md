# Google Takeout EXIF Injector

A Python tool to restore missing EXIF metadata from Google Photos JSON files back into your media files after a Google Takeout export.

## 🎯 Problem

When you export your photos from Google Photos via Takeout, Google often strips EXIF data from the files but saves it separately in JSON files. This causes issues when importing to other photo management systems like Immich, PhotoPrism, or Lightroom, as they rely on EXIF data for:

- Photo capture dates
- GPS coordinates
- Face tags
- Favorites
- Descriptions

This tool reads those JSON files and injects the metadata back into your photos and videos.

## ✨ Features

- ✅ **Restores dates** - PhotoTakenTime → EXIF DateTimeOriginal
- ✅ **Restores GPS** - Latitude, longitude, and altitude
- ✅ **Restores face tags** - People → IPTC Keywords (Immich compatible)
- ✅ **Restores favorites** - Favorited → XMP Rating
- ✅ **Restores descriptions** - Captions → IPTC Caption-Abstract
- ✅ **Updates filesystem dates** - Sets file modification time to match photo date
- ✅ **Conflict detection** - Logs files where EXIF ≠ JSON without overwriting
- ✅ **25-hour tolerance** - Handles timezone differences intelligently
- ✅ **Dry-run mode** - Preview changes before applying
- ✅ **Comprehensive logging** - CSV reports for conflicts, errors, and skipped files
- ✅ **EXIF backups** - Saves original EXIF before modification
- ✅ **Recursive processing** - Works on entire folder trees or single files

## 📦 Supported Formats

| Format | Date | GPS | People | Notes |
|--------|------|-----|--------|-------|
| HEIC | ✅ | ✅ | ✅ | Full support |
| JPG/JPEG | ✅ | ✅ | ✅ | Full support |
| MOV | ✅ | ✅ | ❌ | QuickTime videos |
| MP4 | ✅ | ✅ | ❌ | Generic videos |
| PNG | ✅ | ❌ | ❌ | No native GPS support |
| GIF | ✅ | ❌ | ❌ | No native GPS support |
| WEBP | ✅ | ❌ | ❌ | No native GPS support |

**Skipped:** CR2, DNG (RAW files), LRV (low-res videos)

## 🚀 Installation

### Prerequisites

1. **Python 3.7+**
```bash
