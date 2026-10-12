"""使い方タブの説明書（turkish）。節ごとに持つ（第3段 5-2 章）。"""

HELP_TITLE = "Paradox Localization Translator Kullanım Kılavuzu"
STALE_NOTICE = "(Bu bölüm henüz en son sürüme göre güncellenmedi. Bazı bilgiler güncelliğini yitirmiş olabilir.)"

HELP_SECTIONS = [
    ('intro', '''Paradox Localization Translator Ayrıntılı Kılavuzu

'''),
    ('s00_overview', '''【0. Bu uygulamayla neler yapabilirsiniz】
Paradox Interactive oyunlarının yerelleştirme YAML dosyalarını yerel bir LLM veya bulut API'si aracılığıyla seçtiğiniz hedef dile çevirmek için kullanılan bütünleşik bir araçtır.
Basit toplu çevirinin yanı sıra çevrilmemiş metinleri onarma, farkları güncelleme, QA, çevirilerde arama ve düzeltme, modların çeviri durumunu inceleme, mevcut çeviri modlarına farkları uygulama ve önbellek yönetimi sunar.

Desteklenen başlıca oyunlar:
• Crusader Kings III
• Victoria 3
• Hearts of Iron IV
• Stellaris
• Europa Universalis V

'''),
    ('s01_requirements', '''【1. Başlamak için gerekenler】
Yerel LLM kullanacaksanız:
• Ollama veya LM Studio
• Çeviride kullanılacak bir LLM modeli

Bulut API'si kullanacaksanız:
• OpenAI / Anthropic / Gemini / OpenAI uyumlu API için bir API anahtarı

Dağıtılan uygulama Python, Tk/Tcl ve gerekli grafik arayüz bileşenlerini içerir. Kullanıcıların ayrıca Python kurması gerekmez.

'''),
    ('s02_first_checks', '''【2. Uygulamayı açınca ilk kontrol edilecek yerler】
［Ayarlar］ sekmesindeki ［Arayüz dili］ alanından 11 görüntüleme dili arasından seçim yapabilirsiniz. İlk çalıştırmada işletim sisteminin dili kullanılır (desteklenmiyorsa İngilizce). Uygulamayı daha önce kullanan ve henüz arayüz dilini ayarlamayan kullanıcılar için varsayılan dil Japoncadır. Değişiklikler uygulama yeniden başlatıldıktan sonra geçerli olur. Bu ayar, çevirinin hedef dilinden bağımsızdır.

Ekranın üst kısmında iki ayrı LLM durum göstergesi bulunur.

Çeviri LLM'si:
Normal çeviri, fark çevirisi, QA kapsamında yapay zekâyla düzeltme, model hız testleri ve benzeri işlemlerde kullanılır.

Keşif LLM'si:
Çevrilmemiş modları bulmak ve çeviri durumu incelemesindeki belirsiz adayları değerlendirmek için kullanılır.
Keşif için yaklaşık 3B–8B boyutunda hafif bir model önerilir.

「Çeviri LLM son yanıtı (salt okunur)」 ve 「Keşif LLM son yanıtı (salt okunur)」 alanları, ilgili LLM'den gerçekten alınan yanıtları düzenlenemeyen metin olarak gösterir.
Yanıtın tamamını görmek için 「Tam yanıtı aç」 seçeneğini kullanabilirsiniz.

'''),
    ('s03_translate_queue', '''【3. Çeviri / Kuyruk sekmesi】
Normal çevirinin ana çalışma alanı burasıdır.

［Hedef dil］:
İngilizce, Fransızca, Almanca, İspanyolca, Japonca, Korece, Lehçe, Portekizce (Brezilya), Rusça, Basitleştirilmiş Çince ve Türkçe arasından seçim yapabilirsiniz. Her öğeye kuyruğa eklendiği sıradaki hedef dil kaydedilir. Daha sonra dil seçimini değiştirmeniz, eklenmiş öğelerin hedef dilini değiştirmez.

［Ekle］:
YAML dosyaları veya localization/Mod klasörleri ekler. Sürükleyip bırakma da kullanılabilir.

［Seçilenleri kaldır］:
Yalnızca seçili kuyruk öğelerini kaldırır. Kaynak dosyaları silmez.

［Tümünü temizle］:
Çeviri kuyruğunu boşaltır. Kaynak dosyaları veya önbelleği silmez.

［Çeviriyi başlat］:
Öğeleri yukarıdan aşağıya sırayla çevirir.

［Duraklat］:
Mevcut API/LLM yanıtı tamamlandıktan sonra güvenli bir noktada duraklatır.

［Kaydet ve durdur］:
O ana kadarki önbelleği ve oturumu kaydederek işlemi durdurur. Uygulamayı bir sonraki açışınızda devam edebilirsiniz.

［Mevcut çeviriye ayarları uygula］:
Çeviri sırasında model, sağlayıcı, URL, toplu işlem boyutu, paralellik, Sözlük, İngilizce ve Çinceyi birlikte kullanma ayarı veya başka ayarları değiştirdikten sonra bu düğmeye basarsanız, yeni ayarlar bir sonraki toplu işlemden itibaren kullanılır.

［Seçilenlerin üzerine topluca yaz］:
Tamamlanmış çeviriyi kaynak moda veya hedef dil için tespit edilmiş çeviri moduna uygular.
Mevcut bir çeviri modu varsa, onay ekranında 「Evet」 seçeneği farkları çeviri moduna yazar; 「Hayır」 kaynak modun üzerine yazar; 「İptal」 işlemi iptal eder. Üzerine yazmadan önce hedef açıkça belirtilir ve bir yedek oluşturulur.

'''),
    ('s04_batch_workers', '''【4. Toplu işlem / paralellik için önerilen ayarlar】
Önerilen üç ayardan birini seçebilirsiniz.

Kararlı (20 / 1): toplu işlem 20 / paralellik 1
• Uzun metinleri çok olan modlar
• İlk kullanım
• Kullanılabilir belleğin az olduğu ortamlar
• Doğru çalıştığını doğrulamaya öncelik vermek istediğiniz durumlar

Standart (40 / 1): toplu işlem 40 / paralellik 1
• Normal kullanım için önerilir
• Hız ve kararlılık arasında denge sağlar

Hızlı (60 / 2): toplu işlem 60 / paralellik 2
• Ollama / LM Studio aynı anda iki isteği işleyebiliyorsa
• Yeterli RAM/VRAM varsa

Genel ölçütler:
• Toplu işlem 1–60: normal aralık
• Toplu işlem 80'in üzerinde: uzun metinlerde atlama ve zaman aşımı olasılığı artar
• Toplu işlem 120'nin üzerinde: önerilmez
• Paralellik 1: en kararlı seçenek
• Paralellik 2: sunucuda paralel işlem etkinse önerilir
• Paralellik 3 veya daha fazla: yerel LLM'lerde bellek baskısı, bekleme kuyrukları ve zaman aşımları artabilir

Bulut API'lerinde öncelikle hizmetin istek hızı sınırlarına uyun.

'''),
    ('s05_llm_settings', '''【5. LLM / çeviri ayarları】
Sağlayıcı:
Ollama / LM Studio / OpenAI / Anthropic / Gemini / OpenAI Compatible arasından seçim yapabilirsiniz.

URL:
Ollama varsayılanı: http://localhost:11434
LM Studio varsayılanı: http://localhost:1234/v1
Bulut hizmetleri için genellikle otomatik olarak ayarlanır.

Model:
Bağlantıyı denetledikten sonra kullanılabilir modeller listesinden seçim yapın.

API anahtarı:
Bulut API'leri içindir. Uygulamanın ayar dosyasına kaydedilmez.

Oyun ön ayarı:
CK3 gibi her oyun için çeviri isteminin yaklaşımını belirler.

Çince tabanlı çeviri:
［Çince tabanlı çeviri］ sekmesine Basitleştirilmiş Çince YAML dosyaları eklediğinizde, çeviri öncelikle Çincenin karakter tabanlı söz varlığını, kurumsal terimlerini ve kendine özgü terimlerini esas alır. İngilizce dosya gerekmez.
Hedef dil olarak Japonca veya Korece seçilebilir. Korece, Doğu Asya'yı konu alan modlar (makam ve kurumlar için çok sayıda Çince karakter kökenli terim içerenler) için uygundur. Batılı unvanlar ve dinî terimler için normal çeviri (İngilizceden) resmî çeviriye daha yakın sonuç verir.

Mevcut Japoncadaki çevrilmemiş metinleri onarma:
l_japanese içinde İngilizce veya başka bir dil kalmışsa, yalnızca bu kısımlar onarım için seçilir.

［Çeviri sonrası yedekle, otomatik QA çalıştır ve hataları düzelt］:
Çeviriden sonra hedef dile göre çevrilmemiş metinleri ve Paradox sözdizimindeki bozulmaları denetler.

Basitleştirilmiş Çincede yarım genişlikli boşlukların işlenmesi:
Yalnızca Çince karakterlerle noktalama işaretleri veya parantezler arasındaki yarım genişlikli boşlukları kaldırır. Model kodları ve ekipman adlarındaki sözcükler arasındaki boşluklar korunur.

'''),
    ('s06_cache', '''【6. Önbellek】
Her çevirinin bağımsız bir önbelleği vardır. Önbellekler hedef dile göre ayrıldığı için aynı modu başka bir dile çevirseniz de birbirine karışmaz.
Aynı mod güncellendiğinde de önceki önbellek belirlenir ve değişmeyen metinler yeniden çevrilmez.

［Önbelleği görüntüle］:
Seçili kuyruk öğesinin önbellek içeriğini, kayıt sayısını ve kaydedildiği konumu gösterir.

［Önbellek ekle］:
Başka bir translate_cache.json dosyasını mevcut çeviriyle birleştirir.

Fark güncellemesi:
Önceki kaynak metnin source_manifest.json dosyasını güncel kaynak metinle karşılaştırır ve hedef dil için yalnızca yeni veya değişmiş kısımları yeniden çevirir.

'''),
    ('s07_review', '''【7. QA / Karşılaştır ve düzenle sekmesi】
Kaynak metni hedef dildeki çeviriyle karşılaştırır ve sorunları hiyerarşik biçimde gösterir.
YAML dosyalarını sürükleyip bırakarak yükleyebilirsiniz.

Başlıca denetimler:
• Çevrilmemiş metinler
• Eksik anahtarlar
• Yer tutucu uyuşmazlıkları
• [Character...] / $VALUE$ / § renk kodları gibi öğelerde bozulmalar
• Hedef dile uygun olmayan karakter türlerinin karışması (Çince karakterler, kana, hangul, Kiril)
• Kaynak metinle aynı değerler ve kalan İngilizce metinler (özel adlar ve model kodları gibi öğeler denetim dışında tutulabilir)
• Olası yazım hataları ve eksik karakterler (yalnızca Japonca)
• Parantez veya noktalama tutarsızlıkları

Sorunlu bir satırı seçtiğinizde kaynak metni ve çeviriyi yan yana görebilirsiniz.
［Çeviri (düzenlenebilir)］ alanını doğrudan düzenleyip kaydedebilirsiniz. Farklı karakter türleri, kaynak metinle aynı değerler ve kalan İngilizce metinler bazı durumlarda uyarı olarak gösterilir. İçeriği kontrol edip gerekli düzeltmeleri yapın.
Yapay zekâyla düzeltme, mevcut çeviri LLM'sinin ayarlarını kullanır. Ayarları değiştirdikten sonra ［Mevcut çeviri ayarlarını uygula］ düğmesine basın.

'''),
    ('s08_diff', '''【8. Fark inceleyici sekmesi】
Kaynak metni hedef dildeki çeviriyle anahtar bazında yan yana karşılaştırır.
Sürükleyip bırakmayı da destekler.

Sınıflandırma örnekleri:
• Eksik: kaynakta vardır, çeviride yoktur
• Çevrilmemiş: çevirinin kaynak metinle aynı kalması gibi, hedef dilin ölçütlerine göre çevrilmemiş sayılan durumlar
• Yalnızca hedef dilde: anahtar sadece çeviri tarafında vardır (ekranda dilin adı gösterilir)
• Eşleşme var: doğru biçimde eşleşir

［Seçilenleri çevir］:
Yalnızca seçili tek anahtarı çevirir.

［Tüm eksik ve çevrilmemiş anahtarları çevir］:
Yalnızca sorunlu kısımları toplu olarak LLM'ye gönderir.

Fark çevirisi de mevcut çeviri LLM'sinin ayarlarını kullanır.

'''),
    ('s09_search', '''【9. Çeviri araması sekmesi】
Japonca YAML dosyaları/klasörleri arasında arama yapar ve arama sonuçlarından çevirileri doğrudan düzeltmenizi sağlar.

Aranan içerikler:
• Dosya adı
• Yerelleştirme anahtarı
• Japonca metin

Bir sonucu seçtiğinizde mevcut çeviriyi düzenleyebilir ve ［Bu Japonca çeviriyi kaydet］ ile değişikliği kaynak YAML dosyasına uygulayabilirsiniz.

'''),
    ('s10_glossary', '''【10. Sözlük sekmesi】
［Dil］ alanından hedef dili seçerek her dil için ayrı sabit çeviriler kaydedebilirsiniz. Çeviri, QA ve fark incelemesi, ilgili hedef dilin Sözlük verilerini kullanır.
Örnek (Japonca): Grand Campaign → 開辺

［Temel oyundan içe aktar］, çevrilmiş YAML dosyalarından veya modlardan içe aktarma ve çalışma sekmelerindeki ［Otomatik Sözlük oluştur］ işlevleri 11 dilin tamamında kullanılabilir.

İlgili kaynak terim çeviri grubunda yer alıyorsa, LLM istemine yalnızca o terim sunulur.
Çeviri sırasında Sözlük verilerini değiştirirseniz, ayarları mevcut çeviriye uygulayarak değişikliklerin bir sonraki toplu işlemden itibaren kullanılmasını sağlayabilirsiniz.

'''),
    ('s11_models', '''【11. Modeller / Bağlantı sekmesi】
Bağlantı denetimi, model listesi, hız testleri ve profil yönetimi burada yapılır.

Mevcut LLM hızını test et:
O anda seçili olan tek modelin performansını ölçer.

Seçilen modelleri karşılaştır:
En fazla beş model seçerek ortalama işlem süresini, tokens/s değerini ve hata oranını karşılaştırabilirsiniz.

Model profilleri:
Sağlayıcı, URL, model, toplu işlem boyutu, paralellik, oyun ön ayarı ve benzeri ayarları birlikte kaydedebilirsiniz.
Profil eklemenin yanı sıra silmek de mümkündür.

Çeviri/keşif için en son kullanılan sağlayıcı, URL ve model, uygulama bir sonraki açılışında otomatik olarak geri yüklenir. API anahtarları kaydedilmez.

'''),
    ('s12_monitor', '''【12. Çevrilmemiş metin izleme sekmesi】
Çeviri durumu sekmesinde kaydedilen mod konumlarını salt okunur olarak sürekli izler. Otomatik çeviri yapmaz.

İzlenen konumlar:
［Çeviri durumu］ sekmesinde oyun/mod konumunu seçip ［Seçilen konumlardaki modları tara］ işlemini çalıştırdığınızda, bu konum izleme listesine de kaydedilir.

Keşfe özel LLM:
Normal çeviriden farklı bir model belirleyebilirsiniz. Yaklaşık 3B–8B boyutunda hafif bir model önerilir.

［Sürekli izlemeyi başlat］:
İzleme başladıktan sonra aynı düğme ［Sürekli izlemeyi durdur］ olarak değişir ve durum alanında 「● Sürekli izleme」 görünür.

［Yeniden tara］:
İzleme için kaydedilmiş konumlardaki modların çeviri durumunu yeniden inceler.

İzleme sırasında YAML dosyalarının güncellenme zamanı ve boyutu kontrol edilir; yalnızca değişen öğeler çözümlenir. Hafif LLM'ye yalnızca belirsiz adaylar gönderilir.

'''),
    ('s13_status', '''【13. Çeviri durumu sekmesi】
Oyun/mod konumlarının otomatik tespiti, incelenecek konumların seçimi ve modların çeviri durumunun incelenmesi bu sekmede bir araya getirilmiştir.
Birden fazla konum seçip ［Seçilen konumlardaki modları tara］ işlemini çalıştırabilirsiniz. Sonuçlar hedef dile göre önbelleğe alınır ve yalnızca değişen modlar yeniden incelenir. v0.13'e güncelledikten sonra incelemeyi yeniden yapın; sınıflandırma yöntemi değişmiştir.

Görüntüleme örnekleri:
• Çeviri yok
• Eksikler var
• Başka mod çevirisi eksik
• Başka mod ile tam çeviri
• Çeviri var

Çeviri modu tespiti:
Kaynak modda hedef dil bulunmasa bile, aynı oyundaki başka bir mod kaynak anahtarlara karşılık gelen çeviri anahtarlarına sahipse çeviri modu adayı olarak değerlendirilir.
Çevirinin tam mı yoksa eksik mi olduğu da gösterilir. Hedef dil İngilizce olduğunda, birçok mod zaten İngilizce içerdiğinden haricî çeviri modlarıyla eşleştirme yapılmaz.

［Kapsamlı tanılama］ sekmesi de tanılama ve ilişkilendirmeyi hedef dile göre yapar. Japonca dışındaki diller için eşleştirmeler gerçek verilerle daha az doğrulandığından, üzerine yazmadan önce ilişkiyi kontrol edin.

Ara:
Sınıflandırılmış listeyi daraltmak için mod adı veya durum girin.

Normal çeviri kuyruğuna ekle / Çince tabanlı kuyruğa ekle:
Birden fazla mod seçtiğinizde, seçilenlerin tamamını normal çeviri kuyruğuna ekleyebilirsiniz. Çince tabanlı kuyrukta ise seçili modlardan Çince yerelleştirme içerenlerin tamamı eklenir.

Seçilen modlar hariç normal çeviri kuyruğuna ekle / Seçilen modlar hariç Çince tabanlı kuyruğa ekle:
Yalnızca seçili modları hariç tutar ve kalanları toplu olarak normal çeviri kuyruğuna ya da yalnızca Çince yerelleştirme içerenleri Çince tabanlı kuyruğa ekler.

Çeviri modunun üzerine yazma:
Hedef dil için mevcut bir çeviri modu varsa, eksik kısımlar kaynak moda değil çeviri moduna fark olarak uygulanır.
Mevcut çeviriler korunur; yalnızca eksik veya çevrilmemiş anahtarlar eklenir ya da güncellenir.
İşlemden önce hedef modun adı ve yolu gösterilir; yedek alınır ve iki kez onay istenir.

［Yalnızca farkları çevir］:
Hedef dil için yalnızca yeni veya değişmiş anahtarları ve eksik çevirileri çevirir.

'''),
    ('s14_data_folder', '''【14. Otomatik oluşturulan dosyalar ve kayıt konumu】
Otomatik oluşturulan tüm dosyalar tek klasörde toplanır.

Varsayılan:
書類/Documents/Paradox Localization Translator/

Yapı:
Paradox Localization Translator/
├── 翻訳結果/
├── キャッシュ/
├── バックアップ/
├── ログ/
├── 作業データ/
└── 設定/

Çeviri çıktı klasörleri de hedef dile göre ayrılır. Klasör adları 「…_japanese」, 「…_french」 gibi son ekler taşır ve ilgili dilin YAML dosyaları bu klasörlerde saklanır.

Önceki sürümlerin çalıştırılabilir dosyasının yanındaki ParadoxLocalizationTranslator_Data klasörü açılışta tespit edilir; gerekli veriler eski verilere zarar verilmeden bu kayıt konumuna aktarılır. Devam ettirilen oturumlardaki eski mutlak yollar da güncel kayıt konumuna göre yeniden yorumlanır.

［Ayarlar］ sekmesindeki ［Konumu değiştir］ seçeneğiyle başka bir SSD veya istediğiniz bir klasörü seçebilirsiniz. Mevcut verileri kopyalayarak geçiş yapmak da mümkündür.

'''),
    ('s15_logs_diagnostics', '''【15. Hata günlükleri / tanılama】
Uygulama istisnaları, LLM bağlantı hataları, YAML çözümleme hataları, yazma hataları ve benzeri sorunlar güne göre ayrılmış günlüklere kaydedilir.

［Hata günlüklerini aç］:
Günlük klasörünü açar.

［Tanılama günlüklerini topla］:
İşletim sistemi, uygulama sürümü, model bilgileri, hata günlükleri ve benzeri verileri bir tanılama ZIP dosyasında toplar. API anahtarları ve çeviri metinleri dahil edilmez.

'''),
    ('s16_close_button', '''【16. × düğmesine bastığınızda】
Sağ/sol üst köşedeki × düğmesine bastığınızda varsayılan olarak şu onay sorusu görünür:

「Pencere simge durumuna küçültülsün mü, yoksa uygulamadan çıkılsın mı?」

Simge durumuna küçült:
• Yalnızca pencereyi simge durumuna küçültür
• Çeviri, keşif ve LLM işlemleri durmaz

Çıkış:
• Çeviri kuyruğunda tamamlanmamış öğeler varsa oturumu kaydeder
• Başarıyla tamamlanmış kuyruklar geri yüklenecek oturum olarak tutulmaz
• Bir sonraki açılışta geri yüklemeyi reddettiğiniz oturum silinir ve tekrar sunulmaz
• Uygulamadan çıkmadan önce LLM/çeviri işlemlerine güvenli durdurma isteği gönderir

Bu davranışı daha sonra değiştirmek için:
［Ayarlar］ → ［Pencerenin × düğmesinin davranışı］ alanından,
• Her seferinde sor
• Simge durumuna küçült
• Çıkış
seçeneklerinden birini seçebilirsiniz.

'''),
    ('s17_safety', '''【17. Güvenli kullanım için dikkat edilmesi gerekenler】
• Kaynak modun üzerine doğrudan yazmadan önce mutlaka uyarının içeriğini kontrol edin.
• Steam Workshop güncellemeleri elle yapılan değişikliklerin üzerine yazabilir.
• Doğrudan üzerine yazarken otomatik yedek oluşturulur.
• Büyük çevirilerde önce Standart ayar (40 / 1) önerilir.
• Keşif LLM'sinde küçük bir model kullanmak yükü azaltır.
• Bulut API anahtarları kaydedilmez.
• Bir sorun olduğunda tanılama günlüklerini ZIP olarak toplamak, nedenin araştırılmasını kolaylaştırır.

'''),
    ('s18_common_uses', '''【18. Sık kullanılan iş akışları】
Yeni bir modu çevirme:
1. ［Hedef dil］ seçimini yaptıktan sonra modu sürükleyin
2. Çeviri modelini kontrol edin
3. Çeviriyi başlatın
4. QA uygulayın
5. Gerekirse arama yaparak çevirileri düzeltin
6. Tamamlanmış sürümün farklarını modun üzerine yazın

Mevcut bir çeviri modundaki eksikleri giderme:
1. Hedef dili seçip ［Seçilen konumlardaki modları tara］ işlemini çalıştırın
2. Çeviri durumu bölümünde 「Başka mod çevirisi eksik」 durumunu kontrol edin
3. İlgili modu çevirin
4. Çeviri sırasında ［Duraklat］ veya ［Kaydet ve durdur］ kullanılabilir
5. ［Çıktıyı aç］ ile tamamlanmış dosyaları kontrol edin
6. ［Seçilenlerin üzerine topluca yaz］ düğmesine basın; hedef dilin çeviri modu bulunmuşsa onay ekranından üzerine yazılacak hedefi seçin

Mod güncellendikten sonra yalnızca eklenen kısımları çevirme:
1. Hedef dili seçip güncellenmiş modu yeniden ekleyin
2. Önceki önbellek/kaynak metin anlık görüntüsü otomatik olarak belirlenir
3. Fark güncellemesini onaylayın
4. Yalnızca yeni veya değişmiş anahtarları çevirin

Japonca çeviri terimlerini elle düzeltme:
1. Çeviri araması sekmesini açın
2. Anahtar veya Japonca metin arayın
3. Bir sonuç seçin
4. Çeviriyi düzenleyip kaydedin

Bu yardım sekmesi uygulamanın yerleşik kullanım kılavuzudur. Yalnızca dağıtılan sürümü alan kullanıcılar da haricî bir README açmadan temel işlemlerden gelişmiş özelliklere kadar bilgi edinebilir.

'''),
    ('unofficial', '''【Resmî olmayan bir araçtır】
Bu araç, bir kişi tarafından geliştirilen resmî olmayan bir araçtır ve Paradox Interactive şirketiyle ilişkili değildir. Oyunların adları ilgili hak sahiplerinin ticari markalarıdır.
Araç ücretsizdir ve tüm özelliklerini herkes kullanabilir (MIT lisansı).

'''),
    ('publishing', '''【Çevirdiğiniz modları yayımlarken dikkat etmeniz gerekenler】
• Kaynak modun yazarından izin alın. Başkasının modunun çevirisini Steam Workshop gibi yerlerde yayımlarken asıl yazara ulaşarak izin almak yerleşik bir uygulamadır.
• Ücretsiz yayımlayın. Paradox Interactive'in kullanım koşulları, modlar gibi kullanıcı tarafından oluşturulan içeriklerin ücretli erişimin arkasına konulmasına izin vermez (harcanan zaman karşılığında bağış kabul edilebilir).
• Makine çevirisi içeriyorsa bunu açıklamada belirtmeniz, kullanıcıların karar vermesini kolaylaştırır.
'''),
]
SOURCE_HASHES = {'intro': 'dc0e64262c52', 's00_overview': '57e3f61ee91f', 's01_requirements': 'f6c2c4898718', 's02_first_checks': 'ad4282fa15f0', 's03_translate_queue': '38ceaa862083', 's04_batch_workers': '0ad57aad8db6', 's05_llm_settings': 'f50d5592d09b', 's06_cache': '053b8fd863bd', 's07_review': 'effd2b2c02b3', 's08_diff': '047b909759cf', 's09_search': '331764e4826a', 's10_glossary': 'f3d3a966a4a3', 's11_models': '101883be6b22', 's12_monitor': 'b317e0f4bc37', 's13_status': '7273a7c98ae2', 's14_data_folder': '5e1b34c6fa85', 's15_logs_diagnostics': '78e7512742d6', 's16_close_button': 'bf95d994339e', 's17_safety': 'a3ae50ab1c28', 's18_common_uses': '054ef2c9de07', 'unofficial': '4f1fb69113b7', 'publishing': '13a1da9a3844'}
