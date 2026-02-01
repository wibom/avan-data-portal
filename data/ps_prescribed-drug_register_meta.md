This dataset is an extract from the **National Prescribed Drug Register (Läkemedelsregistret)**, covering **2005‑01‑01** to **2022‑03‑31**. Extraction performed 2025‑02‑24. Includes all Predict cohort individuals with recorded dispensings.

The National Board of Health and Welfare provides a variable list online (variables correspond to `colname_silver`):  
https://www.socialstyrelsen.se/globalassets/sharepoint-dokument/dokument-webb/statistik/register-variabelforteckning-lakemedelsregistret.xlsx

**ATC codes and titles.** Records are annotated with ATC codes at multiple levels. Reference: WHO Collaborating Centre for Drug Statistics Methodology (accessed 2025‑06‑12):  
https://atcddd.fhi.no/  
Some codes represent consumables/medical supplies (not part of official WHO ATC). See TLV list:  
https://www.tlv.se/download/18.4d6cf1fa167c5ffddff967/1545218568789/varugrupperingskoder.pdf

**Negative dispensing counts.** Negative values in `dispensed_package_count` represent corrections to earlier events. Each negative post is annotated with a Candidate Corresponding Erroneous Post (`ccep`) identified via matching (same `avanid`, same `atc_code`, opposite quantity). `ccep_datediff` = days between the two; `ccep_filter` marks matched originals with `drop` to enable straightforward exclusion.

**Unmatched ATC codes.** A subset of ATC‑like codes are not found in the WHO reference, including codes beginning with **Y** (consumables or `Y75…`) and some starting with **X** or **Z**. See your artifact notes for counts and categories.
