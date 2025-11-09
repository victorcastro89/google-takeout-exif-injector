```markdown
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
   python --version
   ```

2. **ExifTool**
   ```bash
   # Windows (winget)
   winget install exiftool
   
   # Windows (Chocolatey)
   choco install exiftool
   
   # macOS (Homebrew)
   brew install exiftool
   
   # Linux (apt)
   sudo apt install libimage-exiftool-perl
   ```

### Install Script

```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/google-takeout-exif-injector.git
cd google-takeout-exif-injector

# No dependencies needed beyond standard library!
```

## 📖 Usage

### Basic Examples

**1. Dry-run on a folder (preview changes):**
```bash
python exif_injector.py "Z:\Takeout\Google Fotos\Fotos de 2022" --dry-run
```

**2. Process entire folder (real mode):**
```bash
python exif_injector.py "Z:\Takeout\Google Fotos\Fotos de 2022"
```

**3. Process single file:**
```bash
python exif_injector.py "Z:\Takeout\Google Fotos\IMG_0731.HEIC"
```

**4. Custom output directory:**
```bash
python exif_injector.py "C:\Photos" --dry-run --output "D:\logs"
```

**5. Skip confirmation prompt:**
```bash
python exif_injector.py "C:\Photos" --no-confirm
```

### Command-Line Options

```
usage: exif_injector.py [-h] [--dry-run] [--output OUTPUT] [--no-confirm] target

positional arguments:
  target           Target file or folder (folders processed recursively)

optional arguments:
  -h, --help       Show this help message and exit
  --dry-run        Simulate without making changes (default: False)
  --output OUTPUT  Output directory for logs (default: C:\temp\exif_logs)
  --no-confirm     Skip confirmation prompt in real mode
```

## 🔍 How It Works

### 1. Discovery
Scans for media files and their corresponding JSON metadata files:
- `IMG_0731.HEIC` → `img_0731.heic.supplemental-metadata.json`
- `IMG_0731.HEIC` → `img_0731.heic.suppl.json`

### 2. Comparison
Compares current EXIF with JSON data:
- **Missing** → Will inject
- **Equal** → Skip
- **Different** → Log conflict, don't modify

### 3. Injection
Injects metadata using appropriate EXIF fields per format:

**Photos (HEIC/JPG):**
```
DateTimeOriginal, CreateDate
GPSLatitude, GPSLongitude, GPSAltitude
IPTC:Keywords (for face tags)
XMP:Rating (for favorites)
IPTC:Caption-Abstract (for descriptions)
```

**Videos (MOV/MP4):**
```
CreateDate, MediaCreateDate, TrackCreateDate
Keys:GPSCoordinates
Description
```

### 4. Filesystem Date
Updates the file's modification date to match the photo date (helps Immich/PhotoPrism).

## 📊 Output & Logs

The tool generates CSV reports in the output directory:

- **`conflicts_TIMESTAMP.csv`** - Files where EXIF ≠ JSON
- **`errors_TIMESTAMP.csv`** - Processing errors
- **`skipped_TIMESTAMP.csv`** - Files skipped (RAW, read-only, etc.)
- **`exif_backups/`** - Original EXIF data (text format)

### Sample Output

```
====================================================================
📊 RESUMO DO PROCESSAMENTO
====================================================================
Total de arquivos encontrados: 689
✅ Processados com sucesso:     114
⏭️  Já completos (pulados):      552
⚠️  Conflitos encontrados:       8
❌ Erros:                        3
📄 Sem JSON correspondente:     12
🚫 Pulados (RAW/readonly):      0
====================================================================
```

## 🛡️ Safety Features

1. **Dry-run first** - Always shows what will change before modifying
2. **EXIF backups** - Saves original EXIF to text files
3. **Conflict detection** - Never overwrites when EXIF ≠ JSON
4. **Read-only protection** - Skips files that can't be modified
5. **Validation** - Checks GPS coordinates and timestamps
6. **25-hour tolerance** - Prevents timezone conflicts from blocking updates

## 🐛 Troubleshooting

### "exiftool not found"
Install ExifTool (see Installation section)

### "No JSON found for file"
Google Takeout didn't include JSON for this file. This is normal for:
- Screenshots
- Downloaded images
- Photos without metadata

### "Conflict detected"
The file's EXIF and JSON have different values. Check `conflicts_*.csv` to investigate. Common causes:
- File was edited after upload
- Manual EXIF modifications
- Multiple uploads of same photo

### Unicode errors
Some files have special characters. These are logged in `skipped_*.csv`.

## 🔗 Related Projects

- [Immich](https://github.com/immich-app/immich) - Self-hosted photo management
- [PhotoPrism](https://github.com/photoprism/photoprism) - AI-powered photo app
- [ExifTool](https://exiftool.org/) - The underlying metadata tool

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details

## ⚠️ Disclaimer

This tool modifies your files. While it includes safety features:
- Always backup your photos before running
- Test on a small folder first with `--dry-run`
- Review the conflict logs before proceeding

The authors are not responsible for data loss.

## 🙏 Acknowledgments

- Built for the [Immich](https://immich.app/) community
- Uses [ExifTool](https://exiftool.org/) by Phil Harvey
- Inspired by the pain of Google Takeout exports

---

**Star ⭐ this repo if it helped you recover your photo metadata!**
```
