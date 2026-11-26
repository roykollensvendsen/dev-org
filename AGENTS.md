# Agentarbeid i dev-org-repoet

Dette er korte, repo-spesifikke arbeidsregler. Kravene til arkitektur, fullmakter og leveranse står i [systemspesifikasjonen](dev-org-spesifikasjon.md); den praktiske arbeidsflyten står i [arbeidsprotokollen](docs/development/work-protocol.md).

- Forankre endringer i en backlog-sak med akseptansekriterier. Hvis saken ikke er klar, avklar kriterier, avhengigheter eller kontrakter før implementasjon.
- Les relevante deler av spesifikasjonen og kartlegg berørte moduler, dataeiere, grensesnitt og verifikasjon før du deler opp eller starter parallelt arbeid.
- Foretrekk små, kjørbare ende-til-ende-leveranser. MVP er en modulær monolitt; ikke lag ny tjeneste eller abstraksjon uten et dokumentert behov og reelle konsumenter.
- Ikke la samtidige arbeidere redigere samme filer eller endre samme kontrakt uten koordinering. Utpek én midlertidig ansvarlig for en delt kontrakt, avtal kompatibilitet og test først, og la andre arbeide mot kontrakten med testdobler.
- Bruk isolerte arbeidskopier/branches for parallelle leveranser. Integrer små endringer ofte, og verifiser kombinasjonen som skal flettes med prosjektets dokumenterte kontroller.
- Hvis en avhengighet, testressurs eller grensesnitt blokkerer arbeidet, registrer den konkrete hindringen og foreslå minste avklaring. Ikke lag en konkurrerende kontrakt eller skjul en blokkering med en midlertidig løsning.
- I leveranserapporten oppgi endring, berørte kontrakter, kontroller som faktisk ble kjørt, resultat og gjenstående risiko. Ikke si at noe er verifisert uten bevis.
- Bruk [ferdigheten for parallelt dev-org-arbeid](skills/dev-org-parallel-work/SKILL.md) for oppgaver på tvers av moduler eller arbeid som utføres samtidig av flere agenter.
- Bruk [ferdigheten for vedlikehold av dokumentasjon](skills/dev-org-doc-maintenance/SKILL.md) når du endrer spesifikasjonen, akseptansekrav, arbeidsprotokoller eller arkitekturdiagrammer.
