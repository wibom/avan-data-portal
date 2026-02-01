This dataset is an extract from the **National Cause of Death Register**, covering the period from **1958‑01‑01** to **2022‑03‑31**. It includes all individuals in the Predict cohort with a record in the register within this time span.

**Date of extraction:** 2025‑02‑24

**Official site:** https://www.socialstyrelsen.se/statistik-och-data/register/dodsorsaksregistret/

**ICD sources and notes.** ICD‑10‑SE and ICD‑9‑CM descriptions and hierarchical groupings in this dataset are based on in‑house translations/mappings. Users should verify annotations independently. Key references:
- ICD‑10‑SE TSV: https://www.socialstyrelsen.se/globalassets/sharepoint-dokument/dokument-webb/klassifikationer-och-koder/icd-10-se.tsv  
- CDC ICD‑9‑CM archive: https://archive.cdc.gov/www_cdc_gov/nchs/icd/icd9cm.htm  
  (RTF: https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/ICD9-CM/2011/Appndx12.zip — file `DC_3D12.RTF`)

**Contributing causes.** Up to 17 contributing causes of death are held in `cod_contributing_01`–`cod_contributing_17` (renamed from `MORSAK1`–`MORSAK17`). RO‑variables (`RO1`–`RO48`)—which encode certificate row/ordinal—were **not** in the extract; ordering on the certificate therefore cannot be reconstructed. Guidance on RO coding: see sample certificate (Swedish):  
https://www.socialstyrelsen.se/globalassets/sharepoint-dokument/artikelkatalog/foreskrifter-och-allmanna-rad/bilaga6-dodsorsaksintyg.pdf