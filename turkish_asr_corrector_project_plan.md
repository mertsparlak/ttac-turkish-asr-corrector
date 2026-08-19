Bence burada doğru kararı verdik. Ama projeyi **“Whisper çıktısını Qwen'e verip düzeltmesini öğretelim”** seviyesinde bırakmayalım. Baştan doğru tasarlarsak elimizde dört ayrı gösterilebilir çıktı olur:

**dataset + benchmark + fine-tuned model + çalışan gerçek zamanlı demo.**

Üstelik güncel araştırma da tam bu yönde: Ağustos 2026'da güncellenen Apple/Google bağlantılı ASR correction çalışması, generic büyük LLM'ler yerine gerçek ve sentetik ASR hatalarıyla eğitilmiş yaklaşık 0.5B'lik specialized seq2seq modellerin daha iyi accuracy/latency dengesi verdiğini; generic LLM'lerin özellikle zaten iyi transkriptlerde over-correction yaptığını gösteriyor. 

Ben projeyi aşağıdaki şekilde kilitlerdim.

---

# Projenin adı ve gerçek hedefi

Geçici isim:

**Turkish Technical ASR Corrector — TTAC**

İlk versiyonun problemi kesin olarak şu olsun:

> **Türkçe konuşmalarda ASR tarafından yanlış yazılan Türkçe + İngilizce teknik terimleri ve normal konuşma hatalarını, yalnızca ASR'nin 1-best text çıktısını kullanarak düzeltmek.**

Örneğin:

```text
ASR:
"pay torçta kuda out of memori hatası alıyorum"

TTAC:
"PyTorch'ta CUDA out of memory hatası alıyorum."
```

ve:

```text
ASR:
"kuven üç buçuk modelini anslotla lora ile eğittim"

TTAC:
"Qwen3.5 modelini Unsloth'la LoRA ile eğittim."
```

Ama modelin şunu yapmasını **istemiyoruz**:

```text
ASR:
"Model bugün eğitildi."

Corrector:
"Qwen3.5 modeli bugün başarıyla fine-tune edildi."
```

Bu hallucination.

Temel davranışımız:

```text
CORRECT, DON'T REWRITE.
```

olmalı.

Bu ayrım çok önemli. Güncel ECLM çalışmasında generic LLM'lerin doğru ASR çıktılarında bile gereksiz kelimeler ekleyebildiği ve düşük-WER rejiminde sonucu bozabildiği gösteriliyor. 

---

# 0. Önce araştırma sorularımızı tanımlayalım

Projede tek bir model eğitmek yerine cevaplamak istediğimiz 4 soru olsun:

| Araştırma sorusu | Neden önemli? |
|---|---|
| Fine-tuned corrector gerçekten ASR WER'ini düşürüyor mu? | Projenin temel değeri |
| Qwen 0.6B gibi decoder LLM mi, specialized seq2seq mi daha iyi? | Mimari karşılaştırması |
| General Türkçe data + technical data, yalnızca general datadan daha mı iyi? | Domain adaptation etkisi |
| Whisper hatalarıyla eğitilen model başka ASR sisteminin hatalarını da düzeltebiliyor mu? | Generalization |

Bence özellikle sonuncusu projeyi çok kuvvetlendirir.

Çünkü Qwen3-ASR-0.6B ve 1.7B artık Türkçe dahil 30 dili destekliyor. Dolayısıyla elimizde Whisper dışında güncel, farklı bir ASR ailesiyle cross-ASR test yapma imkânı var. 

---

# 1. Sistemin genel mimarisi

İlk versiyon:

```text
                 AUDIO
                   │
                   ▼
            ┌─────────────┐
            │     ASR     │
            │ Whisper etc │
            └──────┬──────┘
                   │
                   │ "kuven üçü anslotla..."
                   ▼
          ┌─────────────────┐
          │  TTAC Corrector │
          │   0.3B - 2B     │
          └────────┬────────┘
                   │
                   ▼
       "Qwen3'ü Unsloth'la..."
```

TTAC **audio görmeyecek**.

Bu önemli çünkü böylece Whisper'a bağımlı olmaz:

```text
Whisper ────────┐
Qwen3-ASR ──────┤
Deepgram/... ───┼──► TTAC
diğer ASR ──────┘
```

Yani ileride herhangi bir black-box ASR'nin arkasına bile takılabilir.

---

# 2. Projeyi iki track'e bölelim

Bence çok iyi bir deney çıkar.

### Track A — Whisper Specialist

Sadece Whisper hatalarını düzeltmek üzere eğitilecek:

```text
Whisper hypothesis → reference
```

Amaç:

> Whisper postprocessor olarak maksimum performans.

### Track B — Universal Corrector

Training:

```text
Whisper Small
Whisper Turbo
Qwen3-ASR 0.6B
        ↓
aynı corrector
```

Amaç:

> Birden fazla ASR sisteminin hata dağılımını öğrenmek.

Sonunda:

| Model | Whisper test | Qwen-ASR test | Unseen ASR |
|---|---:|---:|---:|
| Whisper-specific | ? | ? | ? |
| Universal | ? | ? | ? |

çıkar.

Bu akademik açıdan da çok daha hoş.

Nitekim specialized ECLM çalışmasında aynı correction modelinin CTC, seq2seq ve transducer tabanlı farklı ASR mimarilerinde generalization gösterebildiği raporlanıyor. 

---

# 3. Ham gerçek veri — Common Voice

Ana general-Turkish kaynağımız:

**Mozilla Common Voice Turkish 26.0.**

17 Haziran 2026 sürümünde Türkçe tarafında:

- 126.723 clip
- 135,64 saat audio
- 130,1 saat validated
- 1.829 speaker

bulunuyor. 

Daha da kullanışlı olan, hazır split'lerde:

| Split | Clip |
|---|---:|
| Train | 41.401 |
| Dev | 11.868 |
| Test | 11.869 |

var. 

**İlk versiyonda bunun tamamını bile kullanmamıza gerek yok.**

41K train clip gayet güzel başlangıç.

---

# 4. Common Voice'ta dikkat etmemiz gereken önemli problem

Burada veriyi direkt kullanmayacağız.

Türkçe Common Voice sayfası, corpus'un önemli kısmının Wikipedia tabanlı olduğunu ve specialized domain coverage'ın şu anda neredeyse olmadığını açıkça gösteriyor; `technology_robotics` gibi domain'lerde mevcut clip sayıları yok denecek kadar az. Ayrıca datasheet bazı metinlerin temizlenmesini öneriyor. 

Yani:

> Common Voice → **general Turkish**

için.

Technical Turkish'i başka yöntemle üreteceğiz.

Ayrıca `â, î, û` gibi Türkçede anlam/fonetik taşıyan karakterleri körlemesine `a/i/u`'ya normalize etmeyeceğiz; datasheet de özellikle bunu yapmamayı öneriyor. 

---

# 5. İkinci gerçek dataset — MediaSpeech Turkish

Bunu özellikle **out-of-domain evaluation** için çok istiyorum.

OpenSLR MediaSpeech Turkish:

**10 saat manually-transcribed media speech** içeriyor ve CC BY 4.0 altında yayımlanıyor. 

Common Voice:

```text
okunmuş kısa cümleler
```

iken MediaSpeech:

```text
YouTube/media konuşması
```

tarzında.

Bu yüzden ben başlangıçta MediaSpeech'i training'e **hiç katmazdım**.

Onu saklarız.

Sonra:

> Common Voice tabanlı corrector gerçek media speech'te generalize ediyor mu?

bakarız.

Bu çok daha dürüst bir test.

---

# 6. Üçüncü evaluation kaynağı — FLEURS Turkish

FLEURS 102 dil için yaklaşık 12 saat/dil seviyesinde parallel speech benchmark olarak tasarlanmış ve Türkçeyi de kapsıyor. 

Bunu da training yerine evaluation tarafında tutmak mantıklı.

Böylece üç test domainimiz olur:

```text
Common Voice
      ↓
read speech / in-domain

MediaSpeech
      ↓
media / natural-ish

FLEURS
      ↓
unseen multilingual benchmark
```

Ve sonra bizim kendi:

```text
Technical Turkish
```

benchmark'ımız.

## Gelecekteki gerçek eğitim verisi aday havuzu

Buradaki ayrımı net tutacağız: Bir corpus'un Türkçe ses ve doğru transkript içermesi, otomatik olarak corrector eğitimine gireceği anlamına gelmez. Eğitim havuzuna yalnızca lisansı ve kaynağı uygun, split/dedup kontrollerinden geçmiş ve kullandığımız ASR sistemlerinde yeterli miktarda gerçek hata üreten corpus'lar alınacak.

| Kaynak | Statü | Gelecekteki rol | Eğitim havuzuna girme koşulu |
|---|---|---|---|
| **Common Voice Turkish 26.0** | Ana kaynak | General-real correction pair'leri | Mevcut kalite, split ve yayınlama kuralları uygulanacak |
| **ISSAI Turkish Speech Corpus** | Şartlı eğitim adayı | Haber, röportaj, talk-show ve belgesel kökenli daha doğal/medya konuşmasından auxiliary-real pair'ler | Kanonik lisans ve kaynak kullanım hakları netleşmeli; speaker/split yapısı, transcript kalitesi ve Common Voice tekrarları denetlenmeli; ASR hata verimi ölçülmeli |
| **Common Voice Spontaneous Speech 4.0 — Turkish** | Küçük yardımcı aday | Spontane genel konuşma davranışını görmek ve gerekirse az miktarda auxiliary pair üretmek | Validated kayıtlar QC'den geçmeli; corpus çok küçük olduğu için ana eğitim kaynağı veya karar taşıyan benchmark sayılmamalı |
| **Kendi TTAC teknik seslerimiz** | Ana domain kaynağı | Gerçek teknik/code-switching correction pair'leri | Açık rıza, speaker-disjoint split, manuel referans ve pronunciation QC tamamlanmalı |
| **Teknik TTS corpus'u** | Ana sentetik domain kaynağı | Terim, ek, marka ve code-switching hata çeşitliliğini ölçeklemek | Gerçek hatalara benzeme oranı ölçülmeli; identity ve yapay hata oranı dengelenmeli |

ISSAI teknik Türkçe corpus'u değildir; bu yüzden kendi teknik verimizin yerine geçmeyecek. Uygun bulunursa Common Voice'un okuma konuşması ağırlığını azaltan **yardımcı gerçek konuşma kaynağı** olacaktır. Tam corpus'u baştan eğitime dökmek yerine önce küçük, temsilî bir örneklemde ASR çalıştırıp actual-error yield, WER dağılımı, transcript kalitesi ve tekrar oranını ölçeceğiz. Yeterli öğrenme sinyali üretmeyen bölümleri sırf saat sayısını büyütmek için kullanmayacağız.

MediaSpeech ve FLEURS bu aday havuzuna alınmayacak; bağımsız genelleme ölçümü yapabilmek için training dışında tutulacak. LDC Turkish Broadcast News, MagicHub ASR-STurkDuSC ve CoVoST 2 de mevcut lisans, erişim, örtüşme ve hedef uyumu koşullarıyla aktif eğitim adayı değildir. Proje ileride özellikle broadcast-news ASR veya speech translation yönüne genişlerse LDC/CoVoST kararı yeniden açılabilir.

Kaynak ve kullanım notları:

- [ISSAI Turkish Speech Corpus](https://issai.nu.edu.kz/issai-datasets/) yaklaşık 218,2 saat ve 186.171 utterance bildiriyor. [Yayıncının lisans/provenance açıklaması](https://huggingface.co/datasets/issai/Turkish_Speech_Corpus/discussions/1) nedeniyle ticari kullanım veya türetilmiş açık model yayınından önce kullanım hakları ayrıca doğrulanacak.
- [Common Voice Spontaneous Speech 4.0 — Turkish](https://mozilladatacollective.com/datasets/cmqi24rxo0046mf07yo82y3ng) yalnızca küçük bir validated Türkçe bölüm içeriyor; katkısı kapsam değil konuşma tarzı çeşitliliği olacak.
- Her harici corpus için `source_dataset`, sürüm, lisans inceleme tarihi, split, source ID, audio hash ve türetilen ASR modeli kaydedilecek. Bir kaynağın statüsü değişirse eski deneylerin yeniden üretilebilmesi için manifest sürümü değiştirilecek.

---

# 7. ASR error pair'leri nasıl oluşturacağız?

En temel işlem çok basit:

Common Voice bize:

```text
audio.wav

Reference:
"Makine öğrenmesi modellerinde doğruluk önemlidir."
```

veriyor.

Biz audio'yu Whisper'a sokuyoruz:

```text
Whisper:

"makina öğrenmesi modellerinde doğruluk önemlidir"
```

Sonra:

```json
{
  "input": "makina öğrenmesi modellerinde doğruluk önemlidir",
  "target": "Makine öğrenmesi modellerinde doğruluk önemlidir."
}
```

oluşturuyoruz.

Bu doğrudan **gerçek ASR error pair**.

---

# 8. Ama tek ASR kullanmayalım

Ben ilk dataset generation'da üç model kullanırdım.

### ASR-A

**Whisper Small**

244M parametre ve yaklaşık 2 GB VRAM ihtiyacı var. 

Neden?

Daha fazla hata üretecek.

Bu bize zengin training signal sağlar.

### ASR-B

**Whisper Large-v3-Turbo**

809M ve resmi Whisper reposuna göre yaklaşık 6 GB VRAM kullanıyor. Turbo, large-v3'ün hızlandırılmış versiyonu. 

Bu bizim:

> gerçekçi güçlü Whisper

baseline'ımız.

### ASR-C

**Qwen3-ASR-0.6B**

Türkçeyi resmi olarak destekliyor. 

Bunun amacı:

> model Whisper'ın spesifik hatalarını mı ezberledi yoksa gerçekten ASR correction mı öğrendi?

sorusuna cevap vermek.

---

# 9. İlk dataset büyüklüğümüz

Hemen 1 milyon örnek üretmeyelim.

Ben ilk ciddi sürümde şöyle ilerlerdim:

### General-real

Common Voice train'den:

**~40K audio**

ve her audio için örneğin:

```text
Whisper Small
Whisper Turbo
```

çıktısı.

Potansiyel olarak:

**~80K hypothesis-reference pair.**

Ama bunların hepsini training'e körlemesine atmayacağız.

---

# 10. Her pair için WER hesaplayacağız

Örneğin:

```text
REFERENCE:
pytorch ile modeli eğittim

ASR:
pay torç ile modeli eğittim
```

WER hesaplanacak.

Ve datasetimizi bucket'layacağız:

```text
identity
WER = 0

low
0 < WER <= 5%

medium
5–15%

high
15–30%

very_high
>30%
```

Kesin yüzdeleri dataset'i gördükten sonra ayarlarız.

Burada amaç hataların dağılımını görmek.

---

# 11. Çok kritik: identity örneklerini silmeyeceğiz

Örneğin ASR:

```text
Bugün toplantıya katıldım.
```

Reference:

```text
Bugün toplantıya katıldım.
```

ise training pair:

```text
Bugün toplantıya katıldım.
→
Bugün toplantıya katıldım.
```

olmalı.

Çünkü modelimizin önemli görevlerinden biri:

> **Bir şey yanlış değilse dokunma.**

Ama dataset'in %90'ının identity olmasını da istemiyoruz.

Güncel ECLM çalışmasında çok temiz sentetik audio'nun çok fazla identity mapping üreterek correction learning signal'ını azalttığı gösteriliyor; hata çeşitliliği TTS kalitesinden daha önemli çıkmış. 

Başlangıç deneyi olarak ben yaklaşık:

```text
%20–30 identity
%70–80 actual-error
```

örneklemeyi **denenecek bir başlangıç hipotezi** olarak koyardım.

Son oranı dev set belirler.

---

# 12. Dataset schema'sını baştan düzgün yapalım

Her row sadece:

```json
{"input":"...","output":"..."}
```

olmasın.

Şöyle tutalım:

```json
{
  "id": "cv26_tr_000001_whisper_turbo",
  "source_dataset": "common_voice_26",
  "source_split": "train",
  "audio_id": "cv26_tr_000001",
  "speaker_id": "hashed_id",

  "asr_engine": "whisper",
  "asr_model": "large-v3-turbo",

  "hypothesis_raw": "pay torçta kuda hatası aldım",
  "reference_raw": "PyTorch'ta CUDA hatası aldım.",

  "hypothesis_normalized": "pay torçta kuda hatası aldım",
  "reference_normalized": "pytorchta cuda hatası aldım",

  "wer_before": 0.4,

  "pair_type": "real_audio",
  "domain": "general",

  "is_identity": false
}
```

Bunun ileride bize ne kadar yarayacağını tahmin edemezsin.

Çünkü:

```text
Whisper-only
technical-only
high-WER
identity
synthetic
real
speaker subset
```

gibi istediğimiz ablation'ı yapabiliriz.

---

# 13. Train/dev/test leakage'i çok sıkı tutacağız

Bu özellikle önemli.

Aynı audio:

```text
Whisper Small hypothesis
Whisper Turbo hypothesis
Qwen hypothesis
```

oluşturabilir.

Bunların hepsi **aynı split'te kalacak**.

Şunu kesinlikle yapmayacağız:

```text
Whisper Small version → train

aynı sesin Whisper Turbo version'ı → test
```

Bu leakage olur.

Ayrıca mümkün olduğu kadar **speaker-disjoint evaluation** yapacağız.

Common Voice zaten `client_id` benzeri speaker identifier sunuyor. 

---

# 14. Sonra technical corpus oluşturacağız

Burası projenin bizi farklılaştıracak tarafı.

Önce bir **Technical Turkish Lexicon** oluşturacağız.

Mesela kategoriler:

| Kategori | Örnek |
|---|---|
| AI/ML | Qwen, Llama, LoRA, QLoRA, Transformers |
| Framework | PyTorch, TensorFlow, JAX |
| Dev | Python, JavaScript, TypeScript, FastAPI |
| Cloud | AWS, Azure, Kubernetes, Docker |
| Database | PostgreSQL, Redis, MongoDB |
| Hardware | CUDA, NVIDIA, RTX, VRAM |
| Tools | GitHub, Hugging Face, Unsloth |
| Metrics | precision, recall, F1, WER |

Başlangıç hedefim:

**500–1.000 teknik terim.**

Ama sadece kelime listesi yeterli değil.

---

# 15. Türkçe ekler burada çok önemli

Örneğin model şunları görebilmeli:

```text
PyTorch
PyTorch'ta
PyTorch'la
PyTorch'tan

Qwen
Qwen'i
Qwen'le
Qwen'de

CUDA
CUDA'da

GitHub
GitHub'a
GitHub'dan
```

Çünkü Türkçe ASR correction'daki ilginç problem tam burada:

> İngilizce proper noun + Türkçe morphology.

Bunu benchmark'ın ayrı kategorisi bile yapardım.

---

# 16. Technical clean sentence corpus

Terimleri doğal cümlelere yerleştiririz.

Örneğin:

```text
Qwen3.5 modelini Unsloth ile QLoRA kullanarak eğittim.

CUDA out of memory hatası batch size çok yüksek olduğu için oluştu.

FastAPI uygulamasını Docker container içinde çalıştırıyorum.

PostgreSQL bağlantısını SQLAlchemy üzerinden yapıyorum.
```

Burada 20–50 bin temiz target sentence oluşturmak çok zor değil.

Ama kalite önemli.

Ben bunu:

```text
LLM generation
      ↓
automatic validation
      ↓
terminology validator
      ↓
duplicate removal
      ↓
small human review
```

şeklinde yapardım.

---

# 17. Technical data'yı nasıl ASR hatasına çevireceğiz?

İkinci büyük pipeline:

```text
CLEAN TECHNICAL TEXT
        ↓
      TTS
        ↓
     AUDIO
        ↓
Whisper Small/Turbo
        ↓
ASR HYPOTHESIS
        ↓
(HYPOTHESIS, CLEAN TEXT)
```

Tam olarak güncel specialized-ASR-correction araştırmasında kullanılan temel yöntem bu: text → TTS → ASR → noisy/clean pair. Araştırma ayrıca birden fazla TTS sistemi/speaker ve gerçek ASR pair'leriyle karıştırmanın error diversity'yi iyileştirdiğini gösteriyor. 

Ama bunu **Phase 1'de yapmayacağız**.

Önce real-audio pipeline çalışacak.

Sonra synthetic.

Bu bizi debug cehenneminden kurtarır.

---

# 18. Sentetik audio'yu fazla temiz yapmayacağız

Bu biraz counter-intuitive.

TTS:

```text
Qwen üç modeli...
```

cümlesini mükemmel üretip Whisper da mükemmel transcribe ederse training pair:

```text
correct → correct
```

olur.

Bize pek signal sağlamaz.

Güncel çalışma daha çeşitli/hataya açık multi-speaker TTS'nin daha faydalı olabildiğini gösteriyor; speaker diversity de performansı artırıyor. 

Dolayısıyla sonra:

```text
multiple voices
background noise
room reverb
compression
different speaking rates
possibly frequency masking
```

deneyeceğiz.

Ama gerçekçi seviyelerde.

---

# 19. Random typo üretmeye güvenmeyelim

Şunu:

```text
PyTorch
→
PyTprch
```

rastgele bozmak kolay.

Ama gerçek ASR hatası:

```text
PyTorch
→
pay torç
```

gibi fonetik.

Specialized ECLM çalışmasında elle tasarlanmış n-gram/text corruption denemelerinin gerçek TTS→ASR hataları kadar iyi çalışmadığı raporlanıyor. 

O yüzden ana sentetik yöntemimiz:

**TTS → ASR.**

Random typo sadece küçük augmentation.

---

# 20. Gold Technical Test Set

Bence projenin en değerli kısmı bu olabilir.

Hazır dataset yerine **kendi küçük benchmark'ımızı kaydetmek** istiyorum.

Örneğin:

```text
500–1.000 technical sentence
```

ve mümkünse birkaç farklı gerçek konuşmacı.

Cümlelerde:

```text
PyTorch
CUDA
Qwen
Kubernetes
Hugging Face
GitHub
PostgreSQL
LoRA
...
```

geçecek.

Audio gerçekten insan tarafından okunacak.

Bu test seti **asla train'e girmeyecek.**

Sonra:

```text
audio
  ↓
Whisper
  ↓
TTAC
```

ölçeceğiz.

Bu synthetic technical testten çok daha güçlü kanıt olur.

---

# 21. Model karşılaştırmamız

Ben en az şu modelleri test ederim:

### Baseline 0 — No correction

```text
ASR transcript
```

olduğu gibi.

Bu en önemli baseline.

---

### Baseline 1 — Generic Qwen

Fine-tune edilmemiş:

```text
Correct the ASR transcription...
```

promptuyla.

Bunun ne kadar overcorrect yaptığını görelim.

---

### Model A — Qwen 0.6B + LoRA

Senin 4050'de bile deneyebileceğimiz model.

Training:

```text
ASR input
↓
correct transcript
```

---

### Model B — ~1.5–2B Qwen + LoRA

Daha büyük linguistic capacity.

---

### Model C — ByT5-small

Burası araştırma açısından çok önemli.

ByT5 byte-level multilingual seq2seq model ve byte-level yapının spelling/noisy-text görevlerinde doğal avantajı var; orijinal çalışma token-level modellere kıyasla noise ve spelling/pronunciation-sensitive görevlerde daha robust olduğunu bildiriyor. 

ByT5'nin typo/diacritics correction görevlerinde de başarılı kullanımları bulunuyor. 

Yani:

```text
Qwen 0.6B LoRA
vs
ByT5 ~300M
```

çok ilginç.

---

# 22. Unsloth burada nerede kullanılacak?

Qwen branch:

```text
Qwen
+
QLoRA
+
Unsloth
```

olacak.

Unsloth'un güncel dokümantasyonu Qwen3 ve Qwen3.5 fine-tuning'i destekliyor. 

ByT5 branch'i ise ben ayrı tutarım:

```text
Transformers
+
Seq2SeqTrainer / PEFT
```

gibi klasik pipeline.

Unsloth'a zorla sokmaya çalışmayız.

Bu daha sağlıklı.

---

# 23. Qwen training format

Instruction uzun olmayacak.

Örneğin:

```text
SYSTEM:
You are a Turkish ASR transcription error corrector.
Correct recognition errors only.
Do not paraphrase, summarize, explain, or add information.
If the transcription is already correct, return it unchanged.
Output only the corrected transcription.

USER:
pay torçta kuda out of memori hatası aldım

ASSISTANT:
PyTorch'ta CUDA out of memory hatası aldım
```

Training boyunca aynı davranış.

JSON istemiyorum.

Çünkü gerçek ürün çıktısı text.

---

# 24. İlk QLoRA ayarlarımız

Bunu ilk experiment için başlangıç noktası kabul ederiz, dogma değil:

```text
Quantization:
4-bit

LoRA rank:
16

alpha:
32

dropout:
0.05

max sequence:
256 / 512

epochs:
2

learning rate:
~1e-4

effective batch:
32 civarı
```

Sonra yalnızca:

```text
r = 16 / 32
LR = 1e-4 / 2e-4
epoch = 1 / 2 / 3
```

gibi küçük bir grid.

**Training loss'a göre model seçmeyeceğiz.**

Dev WER'e göre seçeceğiz.

---

# 25. Evaluation — en önemli kısım

Sadece:

```text
accuracy = 92%
```

demeyeceğiz.

### Metric 1 — WER before

```text
ASR hypothesis
vs
reference
```

### Metric 2 — WER after

```text
corrector output
vs
reference
```

### Metric 3 — Relative WER Reduction

Örneğin:

```text
Whisper WER:      12%
TTAC WER:          8%
```

relative reduction:

```text
(12 - 8) / 12
```

---

# 26. CER de kesin ölçelim

Türkçe ve technical names yüzünden **Character Error Rate** önemli.

Örneğin:

```text
Qwen
Kuven
```

WER:

```text
1 kelime tamamen yanlış
```

der.

CER ise hatanın ne kadar yakın olduğunu gösterir.

Bu bize technical term correction'da daha ince bilgi verir.

---

# 27. Technical Term Accuracy

Kendi metric'imiz.

Örneğin benchmark'ta 1.000 technical entity var.

ASR doğru:

```text
582 / 1000
```

TTAC sonrası:

```text
851 / 1000
```

dersin.

Bu GitHub README'de WER'den bile daha anlaşılır olabilir.

---

# 28. Over-correction Rate

Bunu kesinlikle ana metric yapardım.

Bir test subset'inde:

```text
ASR == reference
```

olan 1.000 sentence olsun.

Model bunların kaçını bozuyor?

Örneğin:

```text
Qwen zero-shot:
187 / 1000 changed incorrectly

Fine-tuned Qwen:
31 / 1000

ByT5:
12 / 1000
```

Bu çok güçlü sonuç.

Çünkü ASR corrector'ın başarısı sadece:

> kaç hata düzeltti?

değil,

> **kaç doğru şeyi bozmadı?**

da.

Specialized-model araştırmasının temel motivasyonlarından biri tam bu over-correction problemi. 

---

# 29. Improvement / Damage oranı

Her sentence'ı üç sınıfa koyacağız:

```text
IMPROVED
WER after < WER before

UNCHANGED
WER after == WER before

DAMAGED
WER after > WER before
```

Örneğin:

| | Ratio |
|---|---:|
| Improved | 31% |
| Unchanged | 66% |
| Damaged | 3% |

Bu çok anlaşılır.

---

# 30. Hallucination metric

Paper'daki fikri Türkçeye uyarlayabiliriz.

Output'ta:

```text
ASR'de olmayan
+
reference'ta olmayan
```

kaç kelime oluşmuş?

Çünkü:

```text
ASR:
modeli dün eğittim

REFERENCE:
modeli dün eğittim

OUTPUT:
Qwen modelini dün eğittim
```

dil olarak mantıklı.

Ama ASR correction olarak **yanlış**.

Specialized ECLM çalışması hallucination'ı benzer biçimde hypothesis ve reference'ta bulunmayan üretilmiş kelimeler üzerinden ölçüyor. 

---

# 31. Evaluation normalization'ı dikkatli yapacağız

İki metric track olacak.

### Normalized ASR metric

Ignore:

```text
capitalization
çoğu punctuation farkı
fazla whitespace
```

Bunun amacı:

> gerçekten yanlış kelime düzeldi mi?

### Raw orthographic metric

Şunları da ölçer:

```text
PyTorch
pytorch

Qwen3.5
qwen üç buçuk

GitHub'a
githuba
```

Burada CER/exact match kullanabiliriz.

Böylece capitalization ile WER'i “hileli” iyileştirmemiş oluruz.

---

# 32. Common Voice'a özel normalizer

Burada İngilizce normalizer'ı körlemesine kullanmayalım.

Örneğin:

```text
I
İ
ı
i
```

Türkçe'de kritik.

Ayrıca:

```text
â
î
û
```

karakterlerini de silmeyeceğiz; Common Voice Türkçe datasheet'i bunu özellikle tavsiye etmiyor. 

Kendi:

```text
normalize_tr_asr()
```

fonksiyonumuzu yazacağız.

---

# 33. Ablation experiments

Bunlar projeyi gerçekten araştırma gibi gösterecek.

| Experiment | Amaç |
|---|---|
| Real only | Common Voice yeterli mi? |
| Synthetic only | TTS data yeterli mi? |
| Real + synthetic | En iyi kombinasyon mu? |
| General only | Technical term başarısı |
| General + technical | Domain adaptation etkisi |
| Whisper only | ASR-specific |
| Multi-ASR | Generalization |
| No identity samples | Over-correction ne oluyor? |
| + identity samples | Conservative davranış |
| 0.6B vs 2B | Scale etkisi |
| Qwen vs ByT5 | Architecture etkisi |

İşte burada gerçekten güzel grafikler çıkar.

---

# 34. V1 dataset planım

İlk ciddi dataset sürümümüzü şöyle hedeflerdim:

```text
GENERAL REAL
~40K Common Voice audio

    × Whisper Small/Turbo
    ↓
~80K raw pairs

filter + balance
    ↓
~40K–60K selected pairs
```

ve:

```text
TECHNICAL SYNTHETIC
20K–50K clean technical sentences
       ↓
TTS
       ↓
ASR
       ↓
20K–50K pairs
```

Toplam kabaca:

**60K–110K kaliteli training pair.**

Bence ilk sağlam model için fazlasıyla yeterli.

1 milyonla başlamanın hiçbir anlamı yok.

Bu sayı **V1 çekirdek hedefidir**; gelecekteki bütün uygun kaynakların toplamı değildir. V1 kanıtları model eğitimini desteklerse, V1.1/V2 genişlemesinde yukarıdaki aday havuzu şu sırayla değerlendirilecek:

1. ISSAI'den küçük ve temsilî bir audit subset'i seç.
2. Aynı ASR ve pair-builder hattından geçir; actual-error yield, identity oranı, WER dağılımı, transcript kusurları ve Common Voice tekrarlarını raporla.
3. Lisans/provenance incelemesi ile veri kalite kapısı birlikte geçilirse yalnızca faydalı ve dengeli pair'leri auxiliary-real katmanına ekle.
4. Common Voice Spontaneous Türkçe kayıtlarını ayrı source tag'iyle işle; sayıları az olduğu için training ağırlığını sınırlı tut ve sonuçlarını ayrıca raporla.
5. Common Voice, ISSAI, spontane, human-technical ve synthetic-technical kaynaklarının oranlarını sabit varsayma; ablation sonuçlarına göre belirle.

MediaSpeech ve FLEURS bu genişlemeden sonra da training'e karıştırılmayacak; benchmark bütünlüğü korunacak.

---

# 35. Benchmark planı

Training dışında kesinlikle ayrı tutacağımız:

```text
Common Voice test
        ↓
general in-domain

MediaSpeech Turkish
        ↓
real media OOD

FLEURS Turkish
        ↓
external OOD

TTAC-Tech-Human
        ↓
our real technical benchmark
```

Bu dört test seti bence README'yi çok güçlü yapar.

---

# 36. Common Voice lisans konusunu düzgün yapalım

Common Voice Turkish 26.0 CC0 olarak sunuluyor; ancak Mozilla Data Collective sayfası aynı zamanda **speaker identity tespitini ve dataset'i yeniden host/re-share etmeyi yasaklıyor**. 

Dolayısıyla en temiz yayınlama yolu:

```text
TTAC dataset generation code
+
Common Voice clip IDs
+
generated ASR hypotheses
+
reconstruction script
```

yayınlamak.

Raw Common Voice audio'yu kendi Hugging Face repo'muza tekrar yüklemekten kaçınırız.

Bu aynı zamanda repository'yi daha küçük yapar.

---

# 37. Repo sonunda böyle görünsün

```text
turkish-asr-corrector/
│
├── README.md
├── LICENSE
│
├── data/
│   ├── manifests/
│   ├── lexicon/
│   └── benchmark/
│
├── scripts/
│   ├── download_commonvoice.py
│   ├── transcribe_whisper.py
│   ├── transcribe_qwen_asr.py
│   ├── build_pairs.py
│   ├── normalize_tr.py
│   ├── compute_wer.py
│   └── build_splits.py
│
├── synthetic/
│   ├── generate_sentences.py
│   ├── tts.py
│   └── augment_audio.py
│
├── training/
│   ├── train_qwen_unsloth.py
│   └── train_byt5.py
│
├── evaluation/
│   ├── evaluate.py
│   ├── metrics.py
│   └── error_analysis.py
│
└── demo/
    └── app.py
```

Bu repository'nin kendisi bile güzel bir portfolio projesi olur.

---

# 38. Demo

Sonunda Gradio benzeri basit bir UI:

```text
┌─────────────────────────────────────────┐
│ 🎤 Record                               │
│                                         │
│ Original ASR                            │
│ --------------------------------------  │
│ kuven üçü anslotla lora ile eğittim     │
│                                         │
│ TTAC Corrected                          │
│ --------------------------------------  │
│ Qwen3'ü Unsloth'la LoRA ile eğittim.    │
│                                         │
│ WER improvement: ...                    │
│ latency: 31 ms                          │
└─────────────────────────────────────────┘
```

İnsan projeyi 5 saniyede anlar.

---

# 39. Bir sınırı baştan kabul edelim

Text-only corrector her hatayı düzeltemez.

Mesela audio aslında:

```text
Berk toplantıya geldi.
```

ASR:

```text
Mert toplantıya geldi.
```

derse text-only model için:

```text
Berk mi?
Mert mi?
```

anlamak imkânsız olabilir.

İkisi de dilbilgisel olarak doğru.

Bu başarısızlık değil, **bilgi eksikliği**.

V2'de bunu:

```text
N-best ASR hypotheses
phonetic information
confidence scores
```

ekleyerek çözmeye çalışabiliriz. Rare-word ASR correction üzerine yakın tarihli çalışmalar da N-best hypotheses ve phonetic context'in over-correction'ı azaltıp nadir kelime düzeltmesini iyileştirebildiğini araştırıyor. 

---

# 40. V2/V3 için çok güzel yollarımız var

V1:

```text
1-best text → corrected text
```

V2:

```text
N-best hypotheses
        ↓
corrected text
```

V3:

```text
ASR text
+
ASR confidence
+
phonetic representation
+
optional domain lexicon
        ↓
correction
```

V4:

```text
meeting-specific dynamic vocabulary

Mert
Ahmet
Qwen
LLMFort
5G4PHealth
Kafein
...
        ↓

context-aware corrector
```

Burada gerçek ürün tarafına bayağı yaklaşırız.

---

# Uygulama sırasını özellikle böyle yapalım

**Phase 1 — Data audit**

Common Voice 26.0 Turkish'i al.

Metadata temizliğini yap.

10K clip'lik pilot subset çıkar.

---

**Phase 2 — Baseline ASR**

Aynı 10K audio'da:

```text
Whisper Small
Whisper Turbo
Qwen3-ASR 0.6B
```

çalıştır.

Henüz hiçbir model eğitme.

İlk raporumuz:

```text
WER
CER
identity ratio
error distributions
common substitutions
```

olsun.

**Bence en kritik ilk adım bu.**

Çünkü belki Whisper Turbo Common Voice'ta %90+ cümleyi zaten doğru çıkaracak.

O zaman dataset stratejimizi değiştirmemiz gerekir.

---

**Phase 3 — Real correction dataset**

ASR outputs + references → pair builder.

Filtre.

Bucket.

Split.

Leakage kontrolü.

---

**Phase 4 — First models**

İlk olarak sadece real-data ile:

```text
Qwen 0.6B LoRA
ByT5-small
```

eğit.

Synthetic data **henüz yok**.

Sonuçları ölç.

---

**Phase 5 — Technical corpus**

500–1.000 term lexicon.

20K+ clean technical sentences.

Türkçe suffix/code-switching coverage.

---

**Phase 6 — Synthetic speech**

Technical sentences:

```text
TTS → ASR → pairs
```

Multi-speaker + acoustic variation.

---

**Phase 7 — Second training**

```text
general real
+
technical synthetic
```

ile modelleri tekrar eğit.

A/B karşılaştır.

---

**Phase 8 — Gold benchmark**

Gerçek insanların okuduğu technical audio.

Train'de kesinlikle yok.

Whisper/Qwen-ASR baseline'ları çıkar.

Corrector sonrası ölç.

---

**Phase 9 — Ablations**

```text
real vs synthetic
0.6B vs ~2B
Qwen vs ByT5
Whisper-specific vs universal
with vs without identity
```

---

**Phase 10 — Release**

Hugging Face:

```text
model weights
LoRA adapter
dataset manifests
benchmark
model card
```

GitHub:

```text
pipeline
training
evaluation
demo
results
```

ve çalışan Gradio demo.

---

# Başarı kriterini de şimdiden koyalım

Ben **“training bitti”**yi başarı saymam.

V1'in başarılı olması için dört şart koyardım:

### 1.

En az bir OOD test setinde:

```text
WER_after < WER_before
```

istatistiksel olarak anlamlı şekilde.

### 2.

Technical human testte açık biçimde technical-term accuracy artmalı.

### 3.

Already-correct subset'te damage/over-correction oranı düşük olmalı.

### 4.

Küçük model local çalışacak kadar hızlı olmalı.

Bunlardan hiçbiri olmuyorsa:

> Proje başarısız.

ve bunu da dürüstçe söyleriz.

Bu şekilde dataset/model hiperparametrelerini değiştirip sonucu zorla “başarılı” göstermemiş oluruz.

---

## Ben ilk deneyde özellikle **training yapmayacağım**

İlk gerçek milestone'umuz şu olmalı:

> **10.000 Türkçe gerçek audio → 3 ASR sistemi → error analysis report.**

Çünkü projenin geri kalanının tamamını o sonuç belirleyecek.

10K clip üzerinde şunları görmeden LoRA'ya dokunmayalım:

```text
Whisper Small WER
Whisper Turbo WER
Qwen3-ASR 0.6B WER

% identity
% substitutions
% deletions
% insertions

en sık 100 hata
proper noun hataları
foreign/English word hataları

ç/ş/ğ/ı/ö/ü hataları
apostrophe hataları
number hataları
technical-like foreign token hataları
```

Bu rapor çıktıktan sonra **datasetimizi gerçek hata dağılımına göre tasarlarız**. Araştırmadaki en önemli bulgu da zaten model boyutundan ziyade training error distribution'ın gerçek ASR hatalarını temsil etmesinin kritik olması. 

Bence burada acele etmeyip bu sırayla gidersek gerçekten ciddi bir şey çıkarabiliriz. **Bir sonraki somut adımımız Common Voice 26.0 Turkish'i indirip 10K pilot seti oluşturan ve Whisper/Qwen3-ASR çıktılarından ilk `pairs.jsonl` + WER/CER raporunu üreten pipeline'ı kurmak** olmalı. Qwen tarafındaki training'i de sonrasında Unsloth'a sokarız; önce modelin öğrenmesi gereken hataların gerçekten ne olduğuna bakalım.
