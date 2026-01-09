# Faktúra Renamer - Inštalačný návod

Program na automatické premenovanie PDF faktúr podľa čísla faktúry.

---

## Čo program robí

- Načíta PDF súbory z vybraného priečinka
- Automaticky rozpozná číslo faktúry (aj z naskenovaných dokumentov)
- Zobrazí náhľad PDF so zvýrazneným číslom
- Po potvrdení premenuje súbor na formát: `číslo_faktúry-pôvodný_názov.pdf`

---

## Inštalácia (Windows)

### Krok 1: Nainštalovať Python

1. Stiahni Python z https://www.python.org/downloads/
2. **DÔLEŽITÉ:** Pri inštalácii zaškrtni ☑️ **"Add Python to PATH"**
3. Klikni "Install Now"

### Krok 2: Nainštalovať Tesseract OCR (pre naskenované faktúry)

1. Stiahni Tesseract z: https://github.com/UB-Mannheim/tesseract/wiki
   - Klikni na najnovší `tesseract-ocr-w64-setup-xxx.exe`
2. Spusti inštalátor
3. **DÔLEŽITÉ:** Pri výbere komponentov zaškrtni aj:
   - ☑️ Additional language data → Slovak
   - ☑️ Additional language data → Czech
4. Nechaj predvolenú cestu `C:\Program Files\Tesseract-OCR\`
5. Dokonči inštaláciu

### Krok 3: Nainštalovať Python knižnice

1. Otvor **Príkazový riadok** (cmd) alebo **PowerShell**
   - Stlač `Win + R`, napíš `cmd`, stlač Enter
2. Zadaj tento príkaz a stlač Enter:

```
pip install pdfplumber pymupdf Pillow pytesseract
```

3. Počkaj kým sa všetko nainštaluje

### Krok 4: Uložiť program

1. Ulož súbor `faktura_renamer_gui.py` do ľubovoľného priečinka
   - Napríklad: `C:\Programy\FakturaRenamer\faktura_renamer_gui.py`

---

## Spustenie programu

### Možnosť A: Dvojklikom
1. Nájdi súbor `faktura_renamer_gui.py`
2. Dvojklik na súbor

### Možnosť B: Z príkazového riadku
1. Otvor cmd alebo PowerShell
2. Napíš:
```
python C:\Programy\FakturaRenamer\faktura_renamer_gui.py
```

### Možnosť C: Vytvoriť odkaz na ploche
1. Pravý klik na plochu → Nový → Odkaz
2. Zadaj cestu: `python "C:\Programy\FakturaRenamer\faktura_renamer_gui.py"`
3. Pomenuj odkaz: `Faktúra Renamer`

---

## Používanie programu

1. **Spusti program**

2. **Vyber priečinok** s PDF faktúrami
   - Klikni "📁 Vybrať..." a nájdi priečinok

3. **Skontroluj OCR status** (vpravo hore)
   - ✓ OCR: Aktívne (zelené) = všetko OK
   - ✗ OCR: Nedostupné (červené) = Tesseract nie je nainštalovaný

4. **Pre každú faktúru:**
   - V ľavom paneli vidíš zoznam PDF súborov
   - V strede vidíš náhľad faktúry
   - Vpravo vidíš nájdené čísla faktúr
   
5. **Vyber číslo faktúry:**
   - Klikni na správne číslo v zozname, ALEBO
   - Zadaj číslo manuálne do poľa "Manuálne zadanie"

6. **Premenuj súbor:**
   - Klikni "✓ PREMENOVAŤ" alebo stlač Enter
   - Program automaticky prejde na ďalší súbor

### Klávesové skratky
- `Enter` - Premenovať
- `Escape` - Preskočiť súbor
- `Ctrl+O` - Otvoriť priečinok

---

## Riešenie problémov

### "OCR: Nedostupné"
- Tesseract nie je nainštalovaný alebo je v inej ceste
- Riešenie: Nainštaluj Tesseract podľa Kroku 2

### Program nenájde číslo faktúry
- Sivé/nekvalitné skeny môžu byť nečitateľné
- Riešenie: Zadaj číslo manuálne

### "pip nie je rozpoznaný príkaz"
- Python nie je v PATH
- Riešenie: Preinštaluj Python a zaškrtni "Add Python to PATH"

### Chyba pri premenovaní (súbor sa používa)
- Máš faktúru otvorenú v inom programe
- Riešenie: Zavri PDF v Adobe Reader alebo inom prehliadači

### Tesseract je v inej ceste
Otvor `faktura_renamer_gui.py` v poznámkovom bloku a nájdi riadok:
```python
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
```
Zmeň cestu podľa toho, kde máš Tesseract nainštalovaný.

---

## Podporované formáty faktúr

Program automaticky rozpoznáva:
- METRO faktúry: `0/0(026)0058/003755`
- Štandardné čísla: `FV2024001`, `2024/00123`
- Variabilné symboly: `1234567890`
- Čísla v zátvorkách: `(058-013068)`

---

## Kontakt

Pri problémoch kontaktuj: [tu doplň kontakt]

---

*Verzia 1.0 | 2025*
