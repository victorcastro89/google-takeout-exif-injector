#!/usr/bin/env python3
r"""
Google Takeout Photos - EXIF Injector from JSON Metadata
Injects missing EXIF data from Google Photos JSON files into media files

Usage:
    python exif_injector.py <target> [options]
    python exif_injector.py "Z:\Takeout\Google Fotos\Fotos de 2022" --dry-run
    python exif_injector.py "Z:\Takeout\Google Fotos\Fotos de 2022\IMG_0731.HEIC"
"""

import json
import subprocess
import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import re

# ============================================================================
# FASE 1: SETUP E ESTRUTURAS BASE
# ============================================================================

# Extensões suportadas por categoria
PHOTO_EXTENSIONS = {'.heic', '.jpg', '.jpeg'}
VIDEO_EXTENSIONS = {'.mov', '.mp4', '.3gp'}
IMAGE_EXTENSIONS = {'.png', '.gif', '.webp'}
SKIP_EXTENSIONS = {'.cr2', '.dng', '.lrv'}  # RAW e low-res videos
ALL_MEDIA_EXTENSIONS = PHOTO_EXTENSIONS | VIDEO_EXTENSIONS | IMAGE_EXTENSIONS

# Campos EXIF por tipo de arquivo
EXIF_DATE_FIELDS = {
    'photo': ['DateTimeOriginal', 'CreateDate'],
    'video': ['CreateDate', 'MediaCreateDate', 'TrackCreateDate'],
    'image': ['DateCreated', 'XMP:DateCreated']
}

EXIF_GPS_FIELDS = ['GPSLatitude', 'GPSLongitude', 'GPSPosition']

# Tolerância de 25 horas para diferenças de timezone
DATE_TOLERANCE_SECONDS = 25 * 3600  # 90000 segundos

@dataclass
class ProcessingStats:
    """Estatísticas de processamento"""
    total_files: int = 0
    processed_success: int = 0
    already_complete: int = 0
    conflicts: int = 0
    errors: int = 0
    no_json: int = 0
    skipped: int = 0
    
    def print_summary(self):
        print("\n" + "="*60)
        print("📊 RESUMO DO PROCESSAMENTO")
        print("="*60)
        print(f"Total de arquivos encontrados: {self.total_files}")
        print(f"✅ Processados com sucesso:     {self.processed_success}")
        print(f"⏭️  Já completos (pulados):      {self.already_complete}")
        print(f"⚠️  Conflitos encontrados:       {self.conflicts}")
        print(f"❌ Erros:                        {self.errors}")
        print(f"📄 Sem JSON correspondente:     {self.no_json}")
        print(f"🚫 Pulados (RAW/readonly):      {self.skipped}")
        print("="*60)

@dataclass
class LogEntry:
    """Entrada de log"""
    filepath: str
    action: str
    details: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

# ============================================================================
# FASE 2: FUNÇÕES AUXILIARES
# ============================================================================

def find_json_for_file(filepath: Path) -> Optional[Path]:
    """
    Busca JSON correspondente ao arquivo de mídia.
    Prioridade: .supplemental-metadata.json > .suppl.json
    """
    # Buscar com nome lowercase (padrão do Google Takeout)
    base_name = filepath.name.lower()
    parent = filepath.parent
    
    # Padrão 1: filename.ext.supplemental-metadata.json
    json1 = parent / f"{base_name}.supplemental-metadata.json"
    if json1.exists():
        return json1
    
    # Padrão 2: filename.ext.suppl.json
    json2 = parent / f"{base_name}.suppl.json"
    if json2.exists():
        return json2
    
    # Buscar qualquer JSON que comece com o nome do arquivo
    for json_file in parent.glob(f"{base_name}*.json"):
        return json_file
    
    return None

def parse_json_metadata(json_path: Path) -> Optional[Dict[str, Any]]:
    """Extrai metadados do JSON do Google Photos"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return {
            'timestamp': data.get('photoTakenTime', {}).get('timestamp'),
            'latitude': data.get('geoData', {}).get('latitude', 0),
            'longitude': data.get('geoData', {}).get('longitude', 0),
            'altitude': data.get('geoData', {}).get('altitude', 0),
            'people': data.get('people', []),
            'favorited': data.get('favorited', False),
            'description': data.get('description', ''),
        }
    except (json.JSONDecodeError, KeyError, IOError) as e:
        print(f"⚠️  Erro ao ler JSON {json_path}: {e}")
        return None

def extract_exif(filepath: Path) -> Dict[str, Any]:
    """Extrai EXIF atual do arquivo usando exiftool"""
    try:
        result = subprocess.run(
            ['exiftool', '-j', '-DateTimeOriginal', '-CreateDate', '-MediaCreateDate',
             '-GPSLatitude', '-GPSLongitude', '-GPSPosition', str(filepath)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return {}
        
        data = json.loads(result.stdout)
        return data[0] if data else {}
    
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError) as e:
        print(f"⚠️  Erro ao extrair EXIF de {filepath.name}: {e}")
        return {}

def validate_gps(lat: float, lon: float) -> bool:
    """Valida coordenadas GPS"""
    if lat == 0 and lon == 0:
        return False
    return -90 <= lat <= 90 and -180 <= lon <= 180

def validate_timestamp(timestamp: Any) -> bool:
    """Valida timestamp Unix"""
    if timestamp is None:
        return False
    try:
        ts = int(timestamp)
        # Validar se está entre 1970 e 2100
        return 0 < ts < 4102444800
    except (ValueError, TypeError):
        return False

def unix_to_exif_date(timestamp: int) -> str:
    """Converte Unix epoch para formato EXIF: YYYY:MM:DD HH:MM:SS"""
    dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
    return dt.strftime('%Y:%m:%d %H:%M:%S')

def backup_exif(filepath: Path, output_dir: Path) -> bool:
    """Salva EXIF atual em arquivo .exif.backup (apenas texto)"""
    try:
        backup_file = output_dir / f"{filepath.name}.exif.backup"
        result = subprocess.run(
            ['exiftool', '-a', '-G1', str(filepath)],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            backup_file.write_text(result.stdout, encoding='utf-8')
            return True
        return False
    except Exception as e:
        print(f"⚠️  Erro ao fazer backup de {filepath.name}: {e}")
        return False

# ============================================================================
# FASE 3: LÓGICA DE COMPARAÇÃO
# ============================================================================

def parse_exif_date(exif_data: Dict, file_type: str) -> Optional[str]:
    """Extrai data do EXIF baseado no tipo de arquivo"""
    fields = EXIF_DATE_FIELDS.get(file_type, [])
    for field in fields:
        if field in exif_data and exif_data[field]:
            return exif_data[field]
    return None

def parse_exif_gps(exif_data: Dict) -> Optional[Tuple[float, float]]:
    """Extrai GPS do EXIF"""
    lat = exif_data.get('GPSLatitude')
    lon = exif_data.get('GPSLongitude')
    
    if lat and lon:
        # Converter de formato DMS para decimal se necessário
        try:
            if isinstance(lat, str):
                lat = dms_to_decimal(lat)
            if isinstance(lon, str):
                lon = dms_to_decimal(lon)
            return (float(lat), float(lon))
        except:
            pass
    
    return None

def dms_to_decimal(dms_str: str) -> float:
    """Converte coordenada DMS (deg min sec) para decimal"""
    # Exemplo: "41 deg 4' 30.85\" S" -> -41.075236
    match = re.match(r'(\d+) deg (\d+)\' ([\d.]+)" ([NSEW])', dms_str)
    if not match:
        return 0.0
    
    deg, min, sec, direction = match.groups()
    decimal = float(deg) + float(min)/60 + float(sec)/3600
    
    if direction in ['S', 'W']:
        decimal = -decimal
    
    return decimal

def compare_dates(exif_date: Optional[str], json_timestamp: Optional[int]) -> str:
    """
    Compara datas. Retorna: 'equal', 'different', 'exif_missing', 'json_missing'
    Tolerância: 25 horas (diferenças de fuso horário)
    """
    if not exif_date and not json_timestamp:
        return 'both_missing'
    if not exif_date:
        return 'exif_missing'
    if not json_timestamp:
        return 'json_missing'
    
    # Converter JSON timestamp para datetime
    json_dt = datetime.fromtimestamp(int(json_timestamp), tz=timezone.utc)
    
    # Parsear EXIF date para datetime
    try:
        # EXIF formato: YYYY:MM:DD HH:MM:SS
        exif_dt = datetime.strptime(exif_date[:19], '%Y:%m:%d %H:%M:%S')
        exif_dt = exif_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return 'different'
    
    # Calcular diferença absoluta
    diff = abs((exif_dt - json_dt).total_seconds())
    
    # Tolerância de 25 horas
    if diff <= DATE_TOLERANCE_SECONDS:
        return 'equal'
    else:
        return 'different'

def compare_gps(exif_gps: Optional[Tuple[float, float]], 
                json_lat: float, json_lon: float) -> str:
    """
    Compara GPS. Retorna: 'equal', 'different', 'exif_missing', 'json_missing'
    """
    json_has_gps = validate_gps(json_lat, json_lon)
    exif_has_gps = exif_gps is not None
    
    if not exif_has_gps and not json_has_gps:
        return 'both_missing'
    if not exif_has_gps:
        return 'exif_missing'
    if not json_has_gps:
        return 'json_missing'
    
    # Comparar coordenadas (sem tolerância)
    exif_lat, exif_lon = exif_gps
    if abs(exif_lat - json_lat) < 0.0001 and abs(exif_lon - json_lon) < 0.0001:
        return 'equal'
    else:
        return 'different'

def detect_conflicts(filepath: Path, exif_data: Dict, json_data: Dict, 
                    file_type: str) -> List[Dict[str, str]]:
    """Detecta conflitos entre EXIF e JSON"""
    conflicts = []
    
    # Conflito de data
    exif_date = parse_exif_date(exif_data, file_type)
    json_timestamp = json_data.get('timestamp')
    
    if validate_timestamp(json_timestamp):
        date_status = compare_dates(exif_date, json_timestamp)
        if date_status == 'different':
            conflicts.append({
                'file': str(filepath),
                'field': 'Date',
                'exif_value': exif_date or 'N/A',
                'json_value': unix_to_exif_date(json_timestamp)
            })
    
    # Conflito de GPS
    exif_gps = parse_exif_gps(exif_data)
    json_lat = json_data.get('latitude', 0)
    json_lon = json_data.get('longitude', 0)
    
    gps_status = compare_gps(exif_gps, json_lat, json_lon)
    if gps_status == 'different':
        conflicts.append({
            'file': str(filepath),
            'field': 'GPS',
            'exif_value': f"{exif_gps}" if exif_gps else 'N/A',
            'json_value': f"{json_lat}, {json_lon}"
        })
    
    return conflicts

# ============================================================================
# FASE 4: INJEÇÃO EXIF POR TIPO
# ============================================================================

def build_exiftool_cmd_photo(filepath: Path, json_data: Dict) -> List[str]:
    """Constrói comando exiftool para fotos (HEIC/JPG/JPEG)"""
    cmd = ['exiftool', '-overwrite_original']
    
    # Data
    if validate_timestamp(json_data.get('timestamp')):
        date_str = unix_to_exif_date(json_data['timestamp'])
        cmd.extend([
            f'-DateTimeOriginal={date_str}',
            f'-CreateDate={date_str}'
        ])
    
    # GPS
    lat = json_data.get('latitude', 0)
    lon = json_data.get('longitude', 0)
    alt = json_data.get('altitude', 0)
    
    if validate_gps(lat, lon):
        lat_ref = 'South' if lat < 0 else 'North'
        lon_ref = 'West' if lon < 0 else 'East'
        cmd.extend([
            f'-GPSLatitude={abs(lat)}',
            f'-GPSLatitudeRef={lat_ref}',
            f'-GPSLongitude={abs(lon)}',
            f'-GPSLongitudeRef={lon_ref}',
            f'-GPSAltitude={abs(alt)}',
            f'-GPSAltitudeRef=Above Sea Level'
        ])
    
    # People tags (IPTC Keywords)
    people = json_data.get('people', [])
    if people:
        names = [p.get('name', '') for p in people if p.get('name')]
        if names:
            keywords = ','.join(names)
            cmd.append(f'-IPTC:Keywords={keywords}')
    
    # Favorite rating
    if json_data.get('favorited'):
        cmd.append('-XMP:Rating=5')
    
    # Description
    desc = json_data.get('description', '').strip()
    if desc:
        cmd.append(f'-IPTC:Caption-Abstract={desc}')
    
    cmd.append(str(filepath))
    return cmd

def build_exiftool_cmd_video(filepath: Path, json_data: Dict) -> List[str]:
    """Constrói comando exiftool para vídeos (MOV/MP4)"""
    cmd = ['exiftool', '-overwrite_original']
    
    # Data (múltiplos campos para vídeo)
    if validate_timestamp(json_data.get('timestamp')):
        date_str = unix_to_exif_date(json_data['timestamp'])
        cmd.extend([
            f'-CreateDate={date_str}',
            f'-MediaCreateDate={date_str}',
            f'-TrackCreateDate={date_str}'
        ])
    
    # GPS (formato texto para QuickTime)
    lat = json_data.get('latitude', 0)
    lon = json_data.get('longitude', 0)
    
    if validate_gps(lat, lon):
        cmd.append(f'-Keys:GPSCoordinates={lat}, {lon}')
    
    # Description
    desc = json_data.get('description', '').strip()
    if desc:
        cmd.append(f'-Description={desc}')
    
    cmd.append(str(filepath))
    return cmd

def build_exiftool_cmd_image(filepath: Path, json_data: Dict) -> List[str]:
    """Constrói comando exiftool para imagens web (PNG/GIF/WEBP)"""
    cmd = ['exiftool', '-overwrite_original']
    
    # Data (XMP para PNG/GIF)
    if validate_timestamp(json_data.get('timestamp')):
        date_str = unix_to_exif_date(json_data['timestamp'])
        cmd.extend([
            f'-DateCreated={date_str}',
            f'-XMP:DateCreated={date_str}'
        ])
    
    # PNG/GIF não suportam GPS nativamente, então não injetamos
    
    # Description
    desc = json_data.get('description', '').strip()
    if desc:
        cmd.append(f'-Description={desc}')
    
    cmd.append(str(filepath))
    return cmd

def update_filesystem_date(filepath: Path, timestamp: int) -> bool:
    """Atualiza File Modification Date do sistema operacional"""
    try:
        dt = datetime.fromtimestamp(int(timestamp))
        # Converter para timestamp Unix para utime
        import os
        atime = os.path.getatime(filepath)  # Manter access time
        mtime = dt.timestamp()
        os.utime(filepath, (atime, mtime))
        return True
    except Exception as e:
        print(f"⚠️  Erro ao atualizar data do filesystem para {filepath.name}: {e}")
        return False

# ============================================================================
# FASE 5: PROCESSAMENTO PRINCIPAL
# ============================================================================

def should_skip_file(filepath: Path) -> Tuple[bool, str]:
    """
    Verifica se arquivo deve ser pulado.
    Retorna: (should_skip, reason)
    """
    # Verificar extensão
    ext = filepath.suffix.lower()
    if ext in SKIP_EXTENSIONS:
        return True, f"RAW/LRV format ({ext})"
    
    if ext not in ALL_MEDIA_EXTENSIONS:
        return True, f"Unsupported extension ({ext})"
    
    # Verificar permissões
    if not filepath.exists():
        return True, "File not found"
    
    if not filepath.is_file():
        return True, "Not a file"
    
    # Verificar se é read-only
    import stat
    if not (filepath.stat().st_mode & stat.S_IWRITE):
        return True, "Read-only file"
    
    # Verificar caracteres especiais no nome
    try:
        filepath.name.encode('utf-8')
    except UnicodeEncodeError:
        return True, "Unicode encoding issue"
    
    return False, ""

def get_file_type(filepath: Path) -> str:
    """Determina tipo do arquivo: photo, video, ou image"""
    ext = filepath.suffix.lower()
    if ext in PHOTO_EXTENSIONS:
        return 'photo'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    elif ext in IMAGE_EXTENSIONS:
        return 'image'
    return 'unknown'

def process_file(filepath: Path, stats: ProcessingStats, logs: Dict[str, List],
                dry_run: bool = True, backup_dir: Optional[Path] = None) -> bool:
    """
    Processa um arquivo de mídia.
    Retorna True se processado com sucesso.
    """
    stats.total_files += 1
    
    # Verificar se deve pular
    should_skip, skip_reason = should_skip_file(filepath)
    if should_skip:
        stats.skipped += 1
        logs['skipped'].append({
            'file': str(filepath),
            'reason': skip_reason
        })
        return False
    
    # Buscar JSON
    json_path = find_json_for_file(filepath)
    if not json_path:
        stats.no_json += 1
        return False
    
    # Parsear JSON
    json_data = parse_json_metadata(json_path)
    if not json_data:
        stats.errors += 1
        logs['errors'].append({
            'file': str(filepath),
            'error': 'Invalid JSON'
        })
        return False
    
    # Validar dados do JSON
    if not validate_timestamp(json_data.get('timestamp')):
        json_data['timestamp'] = None
    
    lat = json_data.get('latitude', 0)
    lon = json_data.get('longitude', 0)
    if not validate_gps(lat, lon):
        # GPS inválido, logar se fora dos limites
        if (lat != 0 or lon != 0) and not (-90 <= lat <= 90 and -180 <= lon <= 180):
            logs['errors'].append({
                'file': str(filepath),
                'error': f'Invalid GPS coordinates: {lat}, {lon}'
            })
    
    # Extrair EXIF atual
    exif_data = extract_exif(filepath)
    if not exif_data and filepath.stat().st_size > 0:
        stats.errors += 1
        logs['errors'].append({
            'file': str(filepath),
            'error': 'Could not read EXIF (corrupted?)'
        })
        return False
    
    # Determinar tipo de arquivo
    file_type = get_file_type(filepath)
    
    # Detectar conflitos
    conflicts = detect_conflicts(filepath, exif_data, json_data, file_type)
    if conflicts:
        stats.conflicts += 1
        logs['conflicts'].extend(conflicts)
        # NÃO processar arquivos com conflitos
        return False
    
    # Verificar se precisa atualizar
    exif_date = parse_exif_date(exif_data, file_type)
    exif_gps = parse_exif_gps(exif_data)
    
    date_status = compare_dates(exif_date, json_data.get('timestamp'))
    gps_status = compare_gps(exif_gps, json_data.get('latitude', 0), 
                            json_data.get('longitude', 0))
    
    # Se ambos já existem e são iguais, pular
    if date_status in ['equal', 'json_missing'] and gps_status in ['equal', 'json_missing', 'both_missing']:
        stats.already_complete += 1
        return False
    
    # Precisa atualizar - construir comando
    if file_type == 'photo':
        cmd = build_exiftool_cmd_photo(filepath, json_data)
    elif file_type == 'video':
        cmd = build_exiftool_cmd_video(filepath, json_data)
    elif file_type == 'image':
        cmd = build_exiftool_cmd_image(filepath, json_data)
    else:
        return False
    
    # Executar ou simular
    if dry_run:
        changes = []
        
        # Mostrar mudanças de data
        if date_status == 'exif_missing' and validate_timestamp(json_data.get('timestamp')):
            changes.append(f"DATE: N/A → {unix_to_exif_date(json_data['timestamp'])}")
        
        # Mostrar mudanças de GPS
        json_lat = json_data.get('latitude', 0)
        json_lon = json_data.get('longitude', 0)
        if gps_status == 'exif_missing' and validate_gps(json_lat, json_lon):
            changes.append(f"GPS: N/A → ({json_lat:.6f}, {json_lon:.6f})")
        
        # Mostrar pessoas
        people = json_data.get('people', [])
        if people:
            names = [p.get('name', '') for p in people if p.get('name')]
            if names:
                changes.append(f"PEOPLE: {', '.join(names)}")
        
        # Mostrar favorito
        if json_data.get('favorited'):
            changes.append("FAVORITE: ★★★★★")
        
        # Mostrar descrição
        desc = json_data.get('description', '').strip()
        if desc:
            desc_preview = desc[:50] + '...' if len(desc) > 50 else desc
            changes.append(f"DESCRIPTION: {desc_preview}")
        
        if changes:
            print(f"[DRY-RUN] {filepath.name}")
            for change in changes:
                print(f"          {change}")
        
        stats.processed_success += 1
        return True
    
    # Fazer backup do EXIF atual
    if backup_dir:
        backup_exif(filepath, backup_dir)
    
    # Executar exiftool
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            stats.errors += 1
            logs['errors'].append({
                'file': str(filepath),
                'error': f'exiftool failed: {result.stderr}'
            })
            return False
        
        # Atualizar filesystem date
        if validate_timestamp(json_data.get('timestamp')):
            update_filesystem_date(filepath, json_data['timestamp'])
        
        stats.processed_success += 1
        print(f"✅ {filepath.name}")
        return True
        
    except subprocess.TimeoutExpired:
        stats.errors += 1
        logs['errors'].append({
            'file': str(filepath),
            'error': 'exiftool timeout (>60s)'
        })
        return False
    except Exception as e:
        stats.errors += 1
        logs['errors'].append({
            'file': str(filepath),
            'error': str(e)
        })
        return False

# ============================================================================
# FASE 6: SCANNER RECURSIVO
# ============================================================================

def scan_directory(root_path: Path) -> List[Path]:
    """Encontra todos os arquivos de mídia recursivamente"""
    media_files = []
    
    print(f"🔍 Escaneando {root_path}...")
    
    for ext in ALL_MEDIA_EXTENSIONS:
        files = list(root_path.rglob(f"*{ext}"))
        media_files.extend(files)
        
        # Case-insensitive para Windows
        files_upper = list(root_path.rglob(f"*{ext.upper()}"))
        media_files.extend(files_upper)
    
    # Remover duplicatas
    media_files = list(set(media_files))
    media_files.sort()
    
    print(f"📁 Encontrados {len(media_files)} arquivos de mídia")
    return media_files

def get_target_files(target: Path) -> List[Path]:
    """
    Obtém lista de arquivos a processar baseado no target.
    Se for arquivo: retorna lista com 1 arquivo
    Se for pasta: escaneia recursivamente
    """
    if target.is_file():
        # Verificar se é arquivo de mídia suportado
        ext = target.suffix.lower()
        if ext in ALL_MEDIA_EXTENSIONS:
            print(f"📄 Arquivo único: {target.name}")
            return [target]
        else:
            print(f"❌ ERRO: Extensão não suportada: {ext}")
            print(f"Extensões suportadas: {', '.join(sorted(ALL_MEDIA_EXTENSIONS))}")
            sys.exit(1)
    
    elif target.is_dir():
        return scan_directory(target)
    
    else:
        print(f"❌ ERRO: Target não encontrado: {target}")
        sys.exit(1)

# ============================================================================
# FASE 7: LOGGING E RELATÓRIOS
# ============================================================================

def save_logs(logs: Dict[str, List], output_dir: Path):
    """Salva logs em arquivos CSV"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # Log de conflitos
    if logs['conflicts']:
        conflict_file = output_dir / f'conflicts_{timestamp}.csv'
        with open(conflict_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['file', 'field', 'exif_value', 'json_value'])
            writer.writeheader()
            writer.writerows(logs['conflicts'])
        print(f"📄 Conflitos salvos em: {conflict_file}")
    
    # Log de erros
    if logs['errors']:
        error_file = output_dir / f'errors_{timestamp}.csv'
        with open(error_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['file', 'error'])
            writer.writeheader()
            writer.writerows(logs['errors'])
        print(f"📄 Erros salvos em: {error_file}")
    
    # Log de arquivos pulados
    if logs['skipped']:
        skipped_file = output_dir / f'skipped_{timestamp}.csv'
        with open(skipped_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['file', 'reason'])
            writer.writeheader()
            writer.writerows(logs['skipped'])
        print(f"📄 Pulados salvos em: {skipped_file}")

# ============================================================================
# FASE 8: ARGUMENTOS E EXECUÇÃO
# ============================================================================

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description='Google Takeout Photos - EXIF Injector from JSON Metadata',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=r"""
Examples:
  # Dry-run em uma pasta (recursivo)
  python exif_injector.py "Z:\Takeout\Google Fotos\Fotos de 2022" --dry-run
  
  # Processar pasta inteira (modo real)
  python exif_injector.py "Z:\Takeout\Google Fotos\Fotos de 2022"
  
  # Processar arquivo único
  python exif_injector.py "Z:\Takeout\Google Fotos\Fotos de 2022\IMG_0731.HEIC"
  
  # Dry-run com output customizado
  python exif_injector.py "C:\Photos" --dry-run --output "D:\logs"
        """
    )
    
    parser.add_argument(
        'target',
        type=str,
        help='Target file or folder to process (folders are processed recursively)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Simulate processing without making any changes (default: False)'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        default=r'C:\temp\exif_logs',
        help=r'Output directory for logs and backups (default: C:\temp\exif_logs)'
    )
    
    parser.add_argument(
        '--no-confirm',
        action='store_true',
        help='Skip confirmation prompt in real mode (use with caution)'
    )
    
    return parser.parse_args()

def main():
    """Função principal"""
    # Parse argumentos
    args = parse_arguments()
    
    # Configuração
    TARGET = Path(args.target)
    OUTPUT_DIR = Path(args.output)
    BACKUP_DIR = OUTPUT_DIR / "exif_backups"
    DRY_RUN = args.dry_run
    NO_CONFIRM = args.no_confirm
    
    # Criar diretórios de output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    # Verificar se target existe
    if not TARGET.exists():
        print(f"❌ ERRO: Target não encontrado: {TARGET}")
        sys.exit(1)
    
    # Verificar se exiftool está disponível
    try:
        subprocess.run(['exiftool', '-ver'], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ ERRO: exiftool não encontrado. Instale com: winget install exiftool")
        sys.exit(1)
    
    print("="*60)
    print("🚀 Google Takeout EXIF Injector")
    print("="*60)
    print(f"📂 Target: {TARGET}")
    print(f"📊 Logs: {OUTPUT_DIR}")
    print(f"🔧 Modo: {'DRY-RUN (simulação)' if DRY_RUN else 'REAL (modificará arquivos)'}")
    print("="*60)
    
    # Obter arquivos a processar
    media_files = get_target_files(TARGET)
    
    if not media_files:
        print("❌ Nenhum arquivo de mídia encontrado!")
        sys.exit(0)
    
    # Estatísticas e logs
    stats = ProcessingStats()
    logs = {
        'conflicts': [],
        'errors': [],
        'skipped': []
    }
    
    # Processar arquivos
    if DRY_RUN:
        print("\n🔍 EXECUTANDO DRY-RUN (nenhum arquivo será modificado)")
        print("="*60)
    else:
        # Confirmação se não for dry-run e não tiver --no-confirm
        if not NO_CONFIRM:
            print(f"\n⚠️  ATENÇÃO: Você está prestes a MODIFICAR {len(media_files)} arquivo(s)!")
            response = input("Digite 'yes' para confirmar: ")
            if response.lower() != 'yes':
                print("❌ Operação cancelada pelo usuário")
                sys.exit(0)
        
        print("\n⚡ EXECUTANDO MODO REAL")
        print("="*60)
    
    for filepath in media_files:
        process_file(filepath, stats, logs, dry_run=DRY_RUN, backup_dir=BACKUP_DIR)
    
    # Mostrar estatísticas
    stats.print_summary()
    
    # Salvar logs
    save_logs(logs, OUTPUT_DIR)
    
    print("\n✅ PROCESSAMENTO CONCLUÍDO!")
    if not DRY_RUN:
        print(f"📁 Backups EXIF salvos em: {BACKUP_DIR}")
    
    if DRY_RUN and stats.processed_success > 0:
        print("\n💡 Para executar modo REAL, rode novamente sem --dry-run:")
        print(f"   python exif_injector.py \"{TARGET}\"")

if __name__ == "__main__":
    main()
