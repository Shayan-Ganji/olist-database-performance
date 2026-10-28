# Stage 2: Database Performance, Index Optimization & Execution Plan Analysis
**دانشجو:** شایان گنجی (Shayan Ganji)  
**آزمایشگاه:** آزمایشگاه فناوری های مالی داتین- ترم سوم  
**محیط پایگاه‌داده:** PostgreSQL 16.4 | دیتابیس `olist_db` (داده‌های Olist برزیل و NYC 311)  

---

**مستندات و گزارش‌های مهندسی:**
- [نسخه فارسی گزارش تحلیلی و تصمیم‌های معماری (report.fa.md)](report.fa.md)
- [English Technical Architecture & Decision Report (report.md)](report.md)
- [نوت‌بوک تحلیلی اجرا شده با نمودارهای تشخیصی (solution.ipynb)](solution.ipynb)

---

## 🛠️ راهنمای اجرا و فرامین خط فرمان (CLI)

```bash
# ۱. نصب پیش‌نیازهای پایتون
pip install -r requirements.txt

# ۲. ایجاد اسکیماها، ساختار جداول و بارگذاری کل ۱.۸۴ میلیون رکورد
python -m src.cli --init-all

# ۳. اجرای آزمون‌های واحد لایه داده (۸ تست مستقل)
python -m unittest discover tests -v

# ۴. اجرای بنچمارک ۵ کوئری تحلیلی در برابر سقف ۲۰۰ میلی‌ثانیه
python -m src.cli --benchmark

# ۵. سنجش هزینه پنهان ایندکس‌ها (Write Amplification و مصرف دیسک)
python -m src.cli --hidden-cost
```

---

## 📂 ساختار مخزن پروژه

```text
stage-2-shayan-ganji/
├── solution.ipynb          # نوت‌بوک اجرا شده تحلیلی همراه با ۴ نمودار خروجی
├── report.fa.md            # گزارش جامع مهندسی، تصمیم‌ها و مصالحه‌ها (فارسی)
├── report.md               # گزارش جامع معماری و کارایی (انگلیسی)
├── requirements.txt        # مانیفست نسخه‌های دقیق بسته‌ها
├── README.md               # راهنمای اجرایی مختصر
├── generate_notebook.py    # اسکریپت اجرای ناهمگام و بازتولید نوت‌بوک
├── src/
│   ├── database/
│   │   ├── connection.py   # مدیریت استخر اتصالات SQLAlchemy و کانتکست منیجر
│   │   ├── loader.py       # موتور بارگذاری فله‌ای بر پایه استریم باینری COPY
│   │   └── populate_snapshot.py # فرآیند محاسبه و ذخیره‌سازی اسنپ‌شات ماهانه
│   ├── analytics/
│   │   ├── queries.py      # تعاریف کوئری‌های ۱ تا ۵ و موتور اندازه‌گیری زمان
│   │   └── hidden_cost.py  # پروفایلر سنجش افت سرعت نوشتن و اندازه ایندکس‌ها
│   └── cli.py              # واسط یکپارچه خط فرمان
├── sql/
│   ├── ddl/
│   │   ├── 01_create_olist_schema.sql  # تعاریف اسکیما، کلیدهای اصلی ترکیبی و قیود
│   │   └── 02_create_indexes.sql       # ایندکس‌های مرکب پوششی
│   ├── views/
│   │   └── 01_create_views.sql         # Viewهای لایه‌بندی شده و جدول اسنپ‌شات
│   └── routines/
│       ├── 01_create_functions.sql     # توابع اسکالر تاخیر تحویل و رده‌بندی NPS
│       └── 02_create_procedures.sql    # پروسیجر تکرارپذیر به‌روزرسانی اسنپ‌شات
└── tests/
    └── test_data_layer.py  # آزمون‌های واحد لایه داده (اتصالات، توابع و پروسیجر)
```
