# AutoEditor

Mikrofon sesine göre otomatik jump-cut yapan, isteğe bağlı sansür uygulayan ve uzun videoyu YouTube için parçalara bölen Türkçe arayüzlü masaüstü aracı.

Uzun bir kayıttan, sadece konuştuğun yerlerin kaldığı temiz parçalar çıkarır — sen sadece "İŞLE" butonuna basarsın. Oyun kaydı, podcast, ders kaydı, tutorial; konuşma + arka plan sesi olan her şey için kullanılabilir.

## Ne yapar?

- **Jump-cut**: Mikrofonun sessiz olduğu yerleri otomatik atar. Oyun sesi sessizliği etkilemez.
- **Argo/küfür sansürü**: Türkçe `Whisper large-v3-turbo` ile transkripti yerelde çıkarır, kullanıcının tanımladığı kelime/öbek listesindeki ifadelerin üzerine bip sesi bindirir. Tek kelime ve çok kelimeli öbek eşleşmesi yapılır, kısmi eşleşme destekli (kök kelime varyantlarını da yakalar).
- **Oyun sesini korur**: Mic kanalına göre keser ama çıktıda oyun sesi + senin sesin karışık durur.
- **Parçalara böl**: Uzun kayıtları hedef dakikaya göre (örn. 15 dk) eşit parçalara ayırır.
- **Intro/outro ekle**: Önceden hazırladığın intro/outro mp4'lerini her parçanın başına/sonuna ekler.
- **Offline**: İnternete bağlanmaz. Whisper modeli ilk açılışta indikten sonra her şey tamamen yerel çalışır.

## Gereksinimler

| Şey | Not |
|---|---|
| **Windows 10/11** | macOS/Linux için derlenmedi, kod uyumlu ama .exe yok |
| **FFmpeg** | PATH'te olmalı. [gyan.dev'den indir](https://www.gyan.dev/ffmpeg/builds/) → bin klasörünü PATH'e ekle |
| **OBS Studio** | Multi-track kayıt için |
| **Python 3.10+** (yalnızca kaynaktan çalıştıracaksan) | .exe sürümünde gerek yok |
| **Disk** | Model için ~1.5 GB, ara dosyalar için 1-2x video boyutu kadar |

GPU **gerekmez**. CPU'da çalışır. 2 saatlik video için CPU transkripsiyonu ~1-2 saat sürebilir; küfür sansürü kapalıysa süre dakikalarla ölçülür.

## OBS ayarları (çok önemli)

Pipeline mikrofonu **ayrı bir ses kanalında** bekler. Bunu açmadan çalışmaz veya yanlış çalışır.

1. **Settings → Output → Output Mode: Advanced** (Simple **DEĞİL**)
2. **Recording sekmesi → Audio Track: 1 ve 2 tikli**
3. **Format: mkv** (mp4 multi-track'te problem çıkarır)
4. **Settings → Audio → Advanced Audio Properties** (Mixer'da bir kanalın yanındaki dişli):
   - **Desktop Audio** (oyun sesi): Tracks → sadece **1** tikli
   - **Mic/Aux** (mikrofonun): Tracks → sadece **2** tikli

Kontrol: bir kayıt al ve PowerShell'de:
```powershell
ffprobe -v error -select_streams a -show_entries stream=index,channels -of compact "C:\yol\kayit.mkv"
```
**İki satır** görmen lazım. Tek satır görüyorsan OBS hâlâ Simple modda.

## Kurulum

### Seçenek 1 — Kaynaktan çalıştır

```powershell
git clone https://github.com/feronline/auto-video-editor.git
cd auto-video-editor
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

### Seçenek 2 — Kendi .exe'ni derle

```powershell
.\build.ps1
```
Çıktı: `dist\AutoEditor\AutoEditor.exe`. Klasörün tamamını istediğin yere taşıyabilirsin, sadece .exe dosyasını taşıma — yanındaki DLL'ler ona gerekli.

## Kullanım

1. **Aç**: `AutoEditor.exe` veya `python run.py`
2. **Video sürükle-bırak** ya da kutuya tıklayıp dosya seç (mkv/mp4)
3. **Ayarları kontrol et**:

| Ayar | Ne işe yarar | Tavsiye |
|---|---|---|
| **Mikrofon track indeksi** | Mic'in hangi audio track'te olduğu (0-bazlı) | OBS'de Track 2'ye attıysan `1` |
| **Oyun sesi track indeksi** | Oyun sesinin track'i | OBS'de Track 1'e attıysan `0` |
| **Oyun sesini çıktıda tut** | Çıktıda oyun sesi olsun mu | Genelde açık |
| **Oyun sesi seviyesi** | Oyun sesinin gain'i | `1.0` orijinal; çok yüksekse `0.5-0.7` |
| **Sessizlik eşiği** | Bu dB altı sessizlik sayılır | Mic'in sessizse `-52`, gürültülüyse `-42` |
| **Min. sessizlik süresi** | Bu kadar süreden kısa sessizlikler kesilmez | `0.9 s` tipik; daha az kesim isteyen `1.5` yapsın |
| **Konuşma öncesi/sonrası padding** | Kelime kenarlarına bırakılan sus payı | `0.25 / 0.40` — kelime sonu yutuluyorsa "sonra"yı artır |
| **Uzun videoyu parçalara böl** | 15dk parçalara böler. Kısa videoda kapat | Çıktı tek video kalsın istiyorsan kapat |
| **Hedef parça uzunluğu** | Parça başına dakika | `15 dk` YouTube için iyi |

4. **Sansür** istiyorsan kutuyu işaretle, listeye her satıra bir kelime ya da öbek yaz (her birine bip basılır). Kısmi eşleşme yapılır, yani köke yazdığın bir kelime çekimli halleriyle de yakalanır. Çok kelimeli öbekler ardışık kelimelerde eşleştirilir.

5. **Intro/Outro** seç (opsiyonel) — hazır mp4'lerini "templates" klasörüne koyabilirsin.

6. **İŞLE** → ilerleme çubuğunu izle. Çıktı `output\<videoadı>\` klasörüne yazılır.

## Sık karşılaşılan sorunlar

**"Bu video N ses kanalı içeriyor" hatası**: OBS multi-track kaydı yapılmamış. Yukarıdaki OBS ayarları bölümünü oku.

**Konuşmam yarıda kesiliyor**: Sessizlik eşiği çok yüksek (örn. -38 dB). Mic'inin seviyesi düşükse -52'ye kadar indir. Bir de "Konuşma sonrası padding"i 0.5-0.6'ya çıkar.

**Hiçbir şey kesilmedi (video aynı uzunluk)**: Tersine, eşik çok düşük olabilir. -52 yerine -42 dene.

**Çıktıda oyun sesi yok**: "Oyun sesini çıktıda tut" tikli mi? OBS'de oyun sesini doğru track'e attın mı?

**Whisper kelimeleri tutarsız yakalıyor**: Mic kalitesi düşükse kaçınılmaz. Küfür listene Whisper'ın muhtemelen üreteceği varyantları da ekle.

## Çıktı

Her video için `output\<videoadı>\` klasörü oluşur:
- Parçalama açıksa: `<isim>_part01.mp4`, `<isim>_part02.mp4`, ...
- Parçalama kapalıysa: `<isim>_edited.mp4`
- Intro/outro varsa: `<isim>_final_part01.mp4`, ...

Ham YouTube'a yükleme için: 1080p60 H.264 + AAC. Tekrar kodlamadan direkt yükleyebilirsin.

## Lisans

MIT. İstediğin gibi kullan, değiştir, dağıt. Garanti yok, sorumluluk almam.

## Katkı

Issue açabilirsin. PR'lara açığım.

---

**Soru/yardım**: [Issues](../../issues) sekmesinde sor.
