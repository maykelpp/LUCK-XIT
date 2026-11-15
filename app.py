from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, redirect
import yt_dlp
import os
import tempfile
import json
from pathlib import Path
import time
import shutil
import requests

app = Flask(__name__)

# Configuraci贸n de directorios temporales
TEMP_DIR = tempfile.gettempdir()
DOWNLOAD_DIR = os.path.join(TEMP_DIR, 'index9')
MEDIA_DIR = os.path.join(DOWNLOAD_DIR, 'media')
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(MEDIA_DIR, exist_ok=True)

# API de TIKWM para TikTok
TIKWM_API = "https://www.tikwm.com/api/"

def is_tiktok_url(url):
    """Detecta si es una URL de TikTok"""
    return 'tiktok.com' in url.lower() or 'vm.tiktok.com' in url.lower()

def get_tiktok_info(url):
    """Obtiene informaci贸n de TikTok usando TIKWM API"""
    try:
        response = requests.post(TIKWM_API, data={
            'url': url,
            'hd': 1
        }, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == 0:
                return data.get('data')
        return None
    except Exception as e:
        print(f"Error en TIKWM API: {e}")
        return None

@app.route('/')
def index():
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), 'index.html')

@app.route('/media/<path:filename>')
def serve_media(filename):
    """Sirve archivos de media para previsualizaci贸n"""
    return send_from_directory(MEDIA_DIR, filename)

@app.route('/preview', methods=['POST'])
def preview():
    """Obtiene informaci贸n y descarga temporal para previsualizaci贸n"""
    try:
        url = request.form.get('url', '').strip()
        if not url:
            return jsonify({'error': 'URL no proporcionada'}), 400

        timestamp = int(time.time() * 1000)

        # ============ TIKTOK CON TIKWM API ============
        if is_tiktok_url(url):
            tiktok_data = get_tiktok_info(url)
            
            if not tiktok_data:
                return jsonify({'error': 'No se pudo obtener informaci贸n de TikTok'}), 500
            
            # Detectar si es galer铆a de im谩genes (slideshow)
            images = tiktok_data.get('images', [])
            
            if images:
                # Es una galer铆a de im谩genes
                return jsonify({
                    'success': True,
                    'type': 'gallery',
                    'platform': 'tiktok',
                    'images': images,
                    'title': tiktok_data.get('title', 'Galer铆a de TikTok'),
                    'thumbnail': images[0] if images else None,
                    'image_count': len(images),
                    'author': tiktok_data.get('author', {}).get('unique_id', 'Desconocido'),
                    'likes': tiktok_data.get('digg_count', 0),
                    'comments': tiktok_data.get('comment_count', 0),
                    'shares': tiktok_data.get('share_count', 0),
                    'music': tiktok_data.get('music_info', {}).get('title', ''),
                    'music_url': tiktok_data.get('music_info', {}).get('play', ''),
                })
            else:
                # Es un video normal
                video_url = tiktok_data.get('hdplay') or tiktok_data.get('play')
                cover = tiktok_data.get('cover')
                
                # Descargar video preview
                video_preview_path = None
                try:
                    if video_url:
                        preview_name = f'preview_tiktok_{timestamp}.mp4'
                        preview_path = os.path.join(MEDIA_DIR, preview_name)
                        
                        video_response = requests.get(video_url, timeout=60, stream=True)
                        if video_response.status_code == 200:
                            with open(preview_path, 'wb') as f:
                                for chunk in video_response.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            video_preview_path = f'/media/{preview_name}'
                except Exception as e:
                    print(f"Error descargando video preview de TikTok: {e}")
                
                # Audio preview (m煤sica del video)
                audio_preview_path = None
                try:
                    music_url = tiktok_data.get('music_info', {}).get('play')
                    if music_url:
                        audio_name = f'preview_tiktok_audio_{timestamp}.mp3'
                        audio_path = os.path.join(MEDIA_DIR, audio_name)
                        
                        audio_response = requests.get(music_url, timeout=30)
                        if audio_response.status_code == 200:
                            with open(audio_path, 'wb') as f:
                                f.write(audio_response.content)
                            audio_preview_path = f'/media/{audio_name}'
                except Exception as e:
                    print(f"Error descargando audio de TikTok: {e}")
                
                return jsonify({
                    'success': True,
                    'type': 'video',
                    'platform': 'tiktok',
                    'title': tiktok_data.get('title', 'Video de TikTok'),
                    'thumbnail': cover,
                    'video_url': video_preview_path,
                    'audio_url': audio_preview_path,
                    'duration': tiktok_data.get('duration', 0),
                    'uploader': tiktok_data.get('author', {}).get('unique_id', 'Desconocido'),
                    'view_count': tiktok_data.get('play_count', 0),
                    'likes': tiktok_data.get('digg_count', 0),
                    'comments': tiktok_data.get('comment_count', 0),
                    'shares': tiktok_data.get('share_count', 0),
                })

        # ============ OTRAS PLATAFORMAS CON YT-DLP ============
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Extraer thumbnails
            thumbnails = info.get('thumbnails', [])
            thumbnail = thumbnails[-1]['url'] if thumbnails else info.get('thumbnail')

            # Descargar versi贸n preview del video
            video_preview_path = None
            try:
                preview_name = f'preview_video_{timestamp}'
                ydl_preview = {
                    'format': 'worst[ext=mp4]/worst',
                    'outtmpl': os.path.join(MEDIA_DIR, f'{preview_name}.%(ext)s'),
                    'quiet': True,
                    'no_warnings': True,
                }

                with yt_dlp.YoutubeDL(ydl_preview) as ydl2:
                    ydl2.download([url])

                for file in os.listdir(MEDIA_DIR):
                    if file.startswith(preview_name):
                        video_preview_path = f'/media/{file}'
                        break
            except Exception as e:
                print(f"Error descargando preview: {e}")

            # Audio preview
            audio_preview_path = None
            try:
                audio_name = f'preview_audio_{timestamp}'
                ydl_audio_preview = {
                    'format': 'bestaudio/best',
                    'outtmpl': os.path.join(MEDIA_DIR, f'{audio_name}.%(ext)s'),
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '64',
                    }],
                    'quiet': True,
                    'no_warnings': True,
                }

                with yt_dlp.YoutubeDL(ydl_audio_preview) as ydl3:
                    ydl3.download([url])

                for file in os.listdir(MEDIA_DIR):
                    if file.startswith(audio_name) and file.endswith('.mp3'):
                        audio_preview_path = f'/media/{file}'
                        break
            except Exception as e:
                print(f"Error descargando audio preview: {e}")

            return jsonify({
                'success': True,
                'type': 'video',
                'platform': 'other',
                'title': info.get('title', 'Sin t铆tulo'),
                'thumbnail': thumbnail,
                'video_url': video_preview_path,
                'audio_url': audio_preview_path,
                'duration': info.get('duration'),
                'uploader': info.get('uploader', 'Desconocido'),
                'view_count': info.get('view_count'),
            })

    except Exception as e:
        return jsonify({'error': f'Error: {str(e)}'}), 500

@app.route('/download', methods=['POST'])
def download():
    """Descarga el video, audio o galer铆a"""
    try:
        url = request.form.get('url', '').strip()
        kind = request.form.get('kind', 'video')

        if not url:
            return jsonify({'error': 'URL no proporcionada'}), 400

        timestamp = int(time.time() * 1000)

        # ============ TIKTOK CON TIKWM API ============
        if is_tiktok_url(url):
            tiktok_data = get_tiktok_info(url)
            
            if not tiktok_data:
                return jsonify({'error': 'No se pudo obtener informaci贸n de TikTok'}), 500
            
            # Galer铆a de im谩genes
            if kind == 'gallery':
                images = tiktok_data.get('images', [])
                if not images:
                    return jsonify({'error': 'No se encontraron im谩genes'}), 404
                
                import zipfile
                zip_filename = f'luck_xit_tiktok_gallery_{timestamp}.zip'
                zip_path = os.path.join(DOWNLOAD_DIR, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for idx, img_url in enumerate(images, 1):
                        try:
                            img_response = requests.get(img_url, timeout=30)
                            if img_response.status_code == 200:
                                img_name = f'imagen_{idx:03d}.jpg'
                                zipf.writestr(img_name, img_response.content)
                        except Exception as e:
                            print(f"Error descargando imagen {idx}: {e}")
                
                return send_file(
                    zip_path,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=zip_filename
                )
            
            # Video
            elif kind == 'video':
                video_url = tiktok_data.get('hdplay') or tiktok_data.get('play')
                if not video_url:
                    return jsonify({'error': 'No se encontr贸 URL del video'}), 404
                
                video_filename = f'luck_xit_tiktok_{timestamp}.mp4'
                video_path = os.path.join(DOWNLOAD_DIR, video_filename)
                
                video_response = requests.get(video_url, timeout=120, stream=True)
                if video_response.status_code == 200:
                    with open(video_path, 'wb') as f:
                        for chunk in video_response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    
                    return send_file(
                        video_path,
                        mimetype='video/mp4',
                        as_attachment=True,
                        download_name=video_filename
                    )
            
            # Audio (m煤sica del TikTok)
            elif kind == 'audio':
                music_url = tiktok_data.get('music_info', {}).get('play')
                if not music_url:
                    return jsonify({'error': 'No se encontr贸 audio'}), 404
                
                audio_filename = f'luck_xit_tiktok_audio_{timestamp}.mp3'
                audio_path = os.path.join(DOWNLOAD_DIR, audio_filename)
                
                audio_response = requests.get(music_url, timeout=60)
                if audio_response.status_code == 200:
                    with open(audio_path, 'wb') as f:
                        f.write(audio_response.content)
                    
                    return send_file(
                        audio_path,
                        mimetype='audio/mpeg',
                        as_attachment=True,
                        download_name=audio_filename
                    )

        # ============ OTRAS PLATAFORMAS CON YT-DLP ============
        output_template = os.path.join(DOWNLOAD_DIR, f'luck_xit_{timestamp}.%(ext)s')

        if kind == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_template,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
            }
            file_extension = 'mp3'
            mimetype = 'audio/mpeg'
        else:  # video
            ydl_opts = {
                'format': 'best[ext=mp4]/best',
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
                'merge_output_format': 'mp4',
            }
            file_extension = 'mp4'
            mimetype = 'video/mp4'

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Buscar archivo descargado
        downloaded_file = None
        for file in os.listdir(DOWNLOAD_DIR):
            if file.startswith(f'luck_xit_{timestamp}') and file.endswith(f'.{file_extension}'):
                downloaded_file = os.path.join(DOWNLOAD_DIR, file)
                break

        if not downloaded_file or not os.path.exists(downloaded_file):
            return jsonify({'error': 'Error al descargar el archivo'}), 500

        download_name = f'luck_xit_{kind}_{timestamp}.{file_extension}'

        return send_file(
            downloaded_file,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )

    except Exception as e:
        return jsonify({'error': f'Error en la descarga: {str(e)}'}), 500

@app.route('/api/music/search', methods=['GET'])
def music_search():
    """Busca catálogo Jamendo y respeta la autorización de descarga por canción."""
    query = request.args.get('q', '').strip()[:160]
    client_id = os.environ.get('JAMENDO_CLIENT_ID', '').strip()
    if not query:
        return jsonify({'results': []})
    if not client_id:
        return jsonify({'error': 'Falta configurar JAMENDO_CLIENT_ID en Render.'}), 503
    try:
        response = requests.get('https://api.jamendo.com/v3.0/tracks/', params={
            'client_id': client_id, 'format': 'json', 'search': query,
            'limit': 25, 'audioformat': 'mp32', 'include': 'licenses'
        }, timeout=15)
        response.raise_for_status()
        payload = response.json()
        if payload.get('headers', {}).get('status') != 'success':
            return jsonify({'error': 'Jamendo no pudo completar la búsqueda.'}), 502
        results = []
        for item in payload.get('results', []):
            track_id = str(item.get('id', ''))
            if not track_id.isdigit():
                continue
            allowed = item.get('audiodownload_allowed') is True
            results.append({
                'id': 'jamendo_' + track_id,
                'trackId': track_id,
                'title': item.get('name', 'Sin título'),
                'artist': item.get('artist_name', 'Artista independiente'),
                'album': item.get('album_name', ''),
                'artwork': item.get('album_image') or item.get('image', ''),
                'duration': item.get('duration', 0),
                'durationText': (str(int(item.get('duration', 0)) // 60) + ':' +
                                 str(int(item.get('duration', 0)) % 60).zfill(2)),
                'audioUrl': item.get('audio', ''),
                'downloadAllowed': allowed,
                'license': item.get('license_ccurl', ''),
                'url': item.get('shareurl', ''),
                'source': 'Jamendo'
            })
        return jsonify({'results': results, 'source': 'Jamendo'})
    except requests.RequestException:
        return jsonify({'error': 'No se pudo conectar con el catálogo Jamendo.'}), 502

@app.route('/api/music/download/<track_id>', methods=['GET'])
def music_download(track_id):
    """Entrega el archivo solo si Jamendo confirma audiodownload_allowed."""
    import re
    client_id = os.environ.get('JAMENDO_CLIENT_ID', '').strip()
    if not client_id:
        return jsonify({'error': 'Falta configurar JAMENDO_CLIENT_ID en Render.'}), 503
    if not re.fullmatch(r'\d{1,20}', track_id):
        return jsonify({'error': 'Identificador de canción no válido.'}), 400
    try:
        check = requests.get('https://api.jamendo.com/v3.0/tracks/', params={
            'client_id': client_id, 'format': 'json', 'id': track_id,
            'include': 'licenses'
        }, timeout=15)
        check.raise_for_status()
        items = check.json().get('results', [])
        if not items:
            return jsonify({'error': 'Canción no encontrada.'}), 404
        if items[0].get('audiodownload_allowed') is not True:
            return jsonify({'error': 'El artista no autoriza descargar esta canción.'}), 403
        return redirect('https://api.jamendo.com/v3.0/tracks/file/?' +
                        requests.compat.urlencode({
                            'client_id': client_id, 'id': track_id,
                            'action': 'download', 'audioformat': 'mp32'
                        }), code=302)
    except requests.RequestException:
        return jsonify({'error': 'No se pudo verificar el permiso de descarga.'}), 502

@app.route('/api/music/lyrics', methods=['GET'])
def music_lyrics():
    """Consulta letras y timestamps disponibles en LRCLIB."""
    artist = request.args.get('artist', '').strip()[:160]
    track = request.args.get('track', '').strip()[:160]
    album = request.args.get('album', '').strip()[:160]
    if not artist or not track:
        return jsonify({'error': 'Se necesita artista y título'}), 400
    try:
        params = {'artist_name': artist, 'track_name': track}
        if album:
            params['album_name'] = album
        response = requests.get('https://lrclib.net/api/get', params=params, timeout=12,
                                headers={'User-Agent': 'LUCK-XIT/1.0 (music module)'})
        if response.status_code == 404:
            return jsonify({'error': 'No hay letras disponibles para esta canción'}), 404
        response.raise_for_status()
        data = response.json()
        return jsonify({'plainLyrics': data.get('plainLyrics'), 'syncedLyrics': data.get('syncedLyrics'),
                        'source': 'LRCLIB'})
    except requests.RequestException as exc:
        return jsonify({'error': 'No se pudo consultar el servicio de letras: ' + str(exc)}), 502


@app.route('/api/music/export-mp3', methods=['POST'])
def music_export_mp3():
    """Añade metadatos ID3 y portada con marca LUCK a un MP3 aportado por el usuario."""
    import re
    from werkzeug.utils import secure_filename
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, error as ID3Error
    from PIL import Image, ImageDraw, ImageFont
    from io import BytesIO

    audio = request.files.get('audio')
    title = request.form.get('title', '').strip()[:160]
    artist = request.form.get('artist', '').strip()[:160]
    album = request.form.get('album', '').strip()[:160]
    cover = request.files.get('cover')
    if not audio or not audio.filename or not audio.filename.lower().endswith('.mp3'):
        return jsonify({'error': 'Selecciona un archivo MP3 válido.'}), 400
    if not title or not artist:
        return jsonify({'error': 'El título y el artista son obligatorios.'}), 400

    work_dir = tempfile.mkdtemp(prefix='luck_music_')
    try:
        safe_name = secure_filename(audio.filename) or 'audio.mp3'
        input_path = os.path.join(work_dir, safe_name)
        audio.save(input_path)
        if os.path.getsize(input_path) > 80 * 1024 * 1024:
            return jsonify({'error': 'El MP3 supera el límite de 80 MB.'}), 413

        image_bytes = None
        if cover and cover.filename:
            raw = cover.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                return jsonify({'error': 'La portada supera el límite de 8 MB.'}), 413
            try:
                im = Image.open(BytesIO(raw)).convert('RGB')
                im.thumbnail((900, 900))
                image_bytes = im
            except Exception:
                return jsonify({'error': 'La portada debe ser JPG, PNG o WEBP válida.'}), 400
        else:
            image_bytes = Image.new('RGB', (900, 900), (5, 18, 34))

        # Marca visible LUCK MUSIC sobre la portada.
        image_bytes = image_bytes.resize((900, 900))
        draw = ImageDraw.Draw(image_bytes, 'RGBA')
        draw.rounded_rectangle((28, 735, 872, 870), radius=28, fill=(0, 0, 0, 175),
                               outline=(0, 230, 255, 220), width=4)
        try:
            font = ImageFont.truetype('DejaVuSans-Bold.ttf', 64)
            small = ImageFont.truetype('DejaVuSans.ttf', 28)
        except Exception:
            font = ImageFont.load_default()
            small = ImageFont.load_default()
        draw.text((60, 750), 'LUCK MUSIC', fill=(0, 240, 255, 255), font=font)
        draw.text((64, 830), 'PERSONAL AUDIO EDITION', fill=(255, 255, 255, 230), font=small)
        image_out = BytesIO()
        image_bytes.save(image_out, format='JPEG', quality=90)
        image_data = image_out.getvalue()

        try:
            tags = ID3(input_path)
        except ID3Error:
            tags = ID3()
        tags.delall('TIT2')
        tags.delall('TPE1')
        tags.delall('TALB')
        tags.delall('APIC')
        tags.add(TIT2(encoding=3, text=title))
        tags.add(TPE1(encoding=3, text=artist))
        if album:
            tags.add(TALB(encoding=3, text=album))
        tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='LUCK MUSIC cover', data=image_data))
        tags.save(input_path, v2_version=3)

        output_name = re.sub(r'[^A-Za-z0-9._ -]+', '_', f'{title} - {artist}')[:150] + '.mp3'
        response = send_file(input_path, mimetype='audio/mpeg', as_attachment=True,
                             download_name=output_name, max_age=0)
        response.call_on_close(lambda: shutil.rmtree(work_dir, ignore_errors=True))
        return response
    except Exception as exc:
        return jsonify({'error': 'No se pudo etiquetar el MP3: ' + str(exc)}), 500
    finally:
        # El archivo se envía desde disco; su limpieza se realiza al terminar la respuesta.
        pass


@app.route('/health')
def health():
    """Endpoint para verificar que el servidor est谩 funcionando"""
    return jsonify({'status': 'ok', 'message': 'LUCK XIT Server Running'})

def cleanup_temp_files():
    """Elimina archivos temporales antiguos"""
    try:
        for file in os.listdir(DOWNLOAD_DIR):
            file_path = os.path.join(DOWNLOAD_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except:
                pass

        for file in os.listdir(MEDIA_DIR):
            file_path = os.path.join(MEDIA_DIR, file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except:
                pass
    except Exception as e:
        print(f"Error limpiando archivos temporales: {e}")

if __name__ == '__main__':
    cleanup_temp_files()
    print("=" * 60)
    print("馃敟 LUCK XIT - Media Downloader Server")
    print("=" * 60)
    print("馃摗 Servidor iniciado en: http://0.0.0.0:8080")
    print("馃寪 Accede desde tu navegador a: http://localhost:8080")
    print("=" * 60)
    print("鉁� Funcionalidades:")
    print("   鉁� TikTok: API TIKWM (videos, galer铆as, audio)")
    print("   鉁� Otras plataformas: yt-dlp")
    print("   鉁� Previsualizaci贸n de videos y audio")
    print("   鉁� Descargas en MP4, MP3 o ZIP")
    print("=" * 60)
    print("鈿狅笍  Requisitos:")
    print("   - pip install flask yt-dlp requests")
    print("   - FFmpeg (para conversi贸n de audio)")
    print("=" * 60)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8081)), debug=False)
