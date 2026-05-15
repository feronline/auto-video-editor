# AutoEditer

OBS oyun kayıtlarını otomatik kesip YouTube için 10-20dk videolar üreten araç.

## Özellikler
- Mikrofon kanalına göre sessiz yerleri tespit edip jump-cut
- Türkçe transkripsiyon (Whisper large-v3-turbo, offline)
- Küfür sansürü (bip)
- Intro/outro template ekleme
- Uzun videoyu parçalara bölme
- PyQt6 arayüz

## Gereksinimler
- Python 3.10+
- FFmpeg (PATH'te)
- OBS multi-track kayıt (Track 1 = oyun sesi, Track 2 = mikrofon)
- MKV format

## Kurulum
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Çalıştırma
```powershell
python -m src.gui
```
