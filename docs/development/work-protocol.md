# Arbeidsprotokoll for parallell utvikling

Protokollen gjør reglene i del 4.2 og 6 av [systemspesifikasjonen](../../dev-org-spesifikasjon.md) anvendelige i det daglige arbeidet. Den gjelder mennesker og agenter. Spesifikasjonen er autoritativ dersom formuleringer avviker.

## Klargjør oppgaven

Før tildeling skal saken ha:

- et avgrenset resultat og observerbare akseptansekriterier;
- berørte komponenter, mapper eller kontrakter etter beste kjente kartlegging;
- eksplisitte avhengigheter og en rekkefølge der arbeid faktisk må vente;
- en lokal verifikasjonsmåte, relevante kontrakt-/integrasjonskontroller og eventuelle eksterne testkrav;
- delte eller knappe ressurser som må reserveres.

Hvis et sentralt grensesnitt ennå ikke er bestemt, opprett først en liten avklaringsoppgave. Ikke tildel flere implementatører til å gjette hvert sitt grensesnitt.

## Tildel og begrens samtidighet

- Ha én ansvarlig for hver leveranse og én midlertidig ansvarlig for en kontrakt som endres på tvers av moduler. Det er ikke en permanent godkjenningsrolle.
- Fordel arbeid etter modulansvar og avhengigheter. Samle sterkt sammenkoblede endringer hos én arbeider eller i én koordinert leveranse.
- Begrens aktivt arbeid per modul når flere endringer treffer samme filer, skjema eller testtilstand. Prioriter oppgaver som frigjør blokkerte arbeidere.
- Bruk en separat arbeidskopi eller git worktree per samtidig leveranse. Del ikke skrivbar testdata eller lokale arbeidskopier mellom parallelle kjøringer.
- Reserver fysiske benker, konto-/API-kvoter og andre knappe ressurser. Bruk simulatorer når de dekker samme forutsetninger.

## Avtal kontrakten før parallell implementasjon

Når en offentlig kontrakt må endres, utpek ansvarlig for skjema/kall, kompatibilitet, feiltyper, eierskap og kontrakttester. Publiser et lite eksempel eller en testdobbel som konsumentene kan utvikle mot. Foretrekk kompatibel innføring: legg til ny støtte, flytt konsumenter, og fjern gammel støtte etterpå. Hvis det ikke går, samordne leveransen og test hele kombinasjonen før integrasjon.

Ikke opprett en ny abstraksjon bare for å fordele arbeid. Bruk eksisterende porter; MVP kjører som modulær monolitt med reelle isolasjonsgrenser for ubetrodd kjøring.

## Integrer kontinuerlig

- Hold endringer små og branches korte. Integrer så snart akseptansekriteriene er oppfylt.
- Kjør relevante komponent- og kontraktkontroller tidlig. Kjør integrasjonskontrollen på den faktiske kombinasjonen som skal flettes; utvid testutvalget ved ukjent påvirkning.
- Avbryt foreldede bygg og testjobber som ingen konsument trenger. Ikke la CI-kø eller en delt testressurs fylles av duplikater.
- Ved konflikt, stopp overlappende skriving, velg én ansvarlig for sammenslåingen og oppdater avhengigheter. Ikke løs konflikt ved å overskrive ukjent arbeid.
- Rapporter hva som er endret, hvilke kontrakter som berøres, hvilke kontroller som faktisk kjørte, resultatet og eventuelle åpne blokkeringer.

## Finn og fjern flaskehalser

Følg minst med på:

- tid fra klar sak til start, og ventetid på avhengigheter;
- aktiv WIP per modul og saker som blokkerer andre;
- merge-konflikter, integrasjonsfeil og omarbeid per kontrakt/modul;
- CI-køtid, kjøretid, gjenbrukte/dupliserte kontroller og feilrate;
- ventetid på knappe workers, testmiljøer og eksterne kvoter.

Bruk målingene til å redusere WIP, avklare eierskap eller forbedre den aktuelle grensen/testen. Ikke øk antall parallelle arbeidere før den observerte flaskehalsen tåler mer arbeid. Antall agenter, commits eller åpne PR-er er ikke i seg selv et mål på framdrift.
