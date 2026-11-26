# Systemdiagrammer

Disse diagrammene viser MVP-arkitekturen beskrevet i [systemspesifikasjonen](../../dev-org-spesifikasjon.md). De er arkitekturvisninger, ikke en erstatning for modulkontraktene eller den operative konfigurasjonen. Oppdater diagrammene sammen med spekken når ansvar eller dataflyt endres.

[Åpne den interaktive arkitektureksploreren](explorer.html) for å navigere fra systemoversikten til moduler og flyter. Eksploreren er en lett, statisk HTML-side med relative lenker, slik at den også kan publiseres under en GitHub Pages-prosjektsti.

## Komponenter og ansvar

![UML-komponentoversikt med porter på kontrolltjenestens rand](system-overview.svg)

[Redigerbar PlantUML-kilde](system-overview.puml)

Oversikten viser portene som små kvadrater på randen av kontrolltjenesten. Inngående porter mottar REST-, MCP-, worker- og webhook-trafikk. Utgående porter kobler kjernen til lagring, board, Git/PR, CI, kjøremiljø og artefakter. Diagrammet viser ansvar og kjøredataflyt; moduler i kontrolltjenesten trenger ikke være egne prosesser.

**Viktige grenser:**

- Dashboard og stemme-/chatklient er parallelle innganger. Stemmeappen kobler direkte til MCP; den går ikke gjennom dashboardet.
- MCP er én protokollinngang med verktøyregister og profiler. Gruppene er moduler, ikke egne serverprosesser. Identitet og policy kontrollerer hvert kall. Rettighetsinnsyn er en lesende modul over de samme identitets- og policybeslutningene; forhåndsvurdering utfører ikke handlingen.
- Arbeideren henter oppdrag via Worker API. Agentmotoren kjører isolert og får ikke kontrolltjenestens hemmeligheter. Eksterne sideeffekter håndheves av gatewayen.
- Lokal boardadapter og A2A er valgfrie eller senere utvidelser. GitHub og PostgreSQL er de valgte MVP-adapterne.

## Porter og adaptere

Tabellen konkretiserer portene som allerede vises på kontrolltjenestens rand i hoveddiagrammet. Portene er modulkontrakter, ikke ekstra nettverkshopp. Piler i UML-bildet viser kjøredataflyt; adapterne avhenger av kontraktene i kode, mens kjernen ikke importerer adapterimplementasjoner.

| Retning | Port | MVP-adapter(e) | Bruk |
|---|---|---|---|
| Inngående | REST / API | REST-adapter | Dashboard og API-klienter kaller brukstilfeller gjennom identitet og policy. |
| Inngående | MCP | MCP-adapter med innsikt-, tilgangs-, arbeid-, meldings- og valgfri administrasjonsgruppe | Stemme- og agentklienter ser bare verktøy som er kvalifisert og tillatt for identiteten. Tilgangsgruppen leser effektive rettigheter og vurderer handlinger uten å utføre dem. Hvert kall går gjennom samme autorisasjon. |
| Inngående | Worker API | Worker-adapter | Arbeidere henter oppgaver, fornyer lease og leverer sjekkpunkt med egen worker-identitet. |
| Inngående | Webhook | GitHub-webhookadapter | Verifiserte issue- og CI-hendelser normaliseres før de påvirker intern tilstand. |
| Inngående · senere | A2A | Ekstern agentadapter | Eksterne agentidentiteter må kobles til en tillitsprofil før svar kan påvirke arbeid. |
| Utgående | Persistence | PostgreSQL-adapter | Intern oppdrags-, lease-, policy-, meldings- og hendelsestilstand lagres transaksjonelt. |
| Utgående | WorkTracking | GitHub Projects/Issues; lokal filadapter for utvikling og lokale arbeidsflyter | Henter og oppdaterer backlog via én aktiv boardadapter per prosjekt. |
| Utgående | Git / PR | GitHub Git/PR-adapter | Publiserer branch og PR idempotent gjennom gatewayen. |
| Utgående | CI status | GitHub Actions-adapter | Leser check runs og avstemmer webhook-resultater. |
| Utgående | ExecutionBackend | Rootless Podman-adapter | Oppretter og avslutter isolert arbeidsområde og agentprosess. |
| Utgående | Artefakter | Artefaktadapter | Sikrer sjekkpunkt, logger og leveranseartefakter med integritetsreferanser. |

## Sekvens: GitHub-sak til verifisert PR

```mermaid
sequenceDiagram
    autonumber
    actor Human as Menneske
    participant GH as GitHub Projects/Issues
    participant Hook as Webhook/API
    participant Board as Board-adapter
    participant API as API v1
    participant Core as Organisasjonskjerne
    participant Policy as Policy
    participant DB as Persistence / PostgreSQL
    participant Worker as Worker
    participant Runtime as Podman-runtime
    participant Agent as Agentadapter / motor
    participant MCP as MCP-server
    participant Gateway as Integrasjonsgateway
    participant Git as Git/PR-adapter
    participant CI as GitHub Actions

    Human->>GH: Oppretter eller prioriterer issue
    GH-->>Hook: Webhook med issue-endring
    Hook->>Board: Verifiser og normaliser hendelsen
    Board->>Core: Endret sak med ekstern ID/revisjon
    Core->>DB: Lagre intern Task-kobling og hendelse
    Core->>Policy: Vurder om saken kan planlegges
    Policy-->>Core: Tillat / avslag / godkjenning kreves
    Core->>DB: Kølegg tillatt arbeid atomisk

    Worker->>API: Be om arbeid
    API->>Core: Autentisert claim-forespørsel
    Core->>Policy: Kontroller mandat, profil og tilgjengelighet
    Policy-->>Core: Tillat claim
    Core->>DB: Opprett lease og fencing token
    DB-->>Worker: Task, mandat, sjekkpunktreferanser
    Worker->>Runtime: Opprett isolert arbeidsområde
    Runtime-->>Worker: Sandbox klar
    Worker->>Agent: Start motor med oppdrag og verktøyprofil
    Agent->>MCP: Les oppdragsstatus / send melding (valgfritt)
    MCP->>API: Kall med worker-identitet
    API->>Core: Validert verktøykall
    Core->>DB: Registrer melding / hendelse
    Core-->>API: Strukturert resultat
    API-->>MCP: Strukturert resultat
    MCP-->>Agent: Strukturert svar
    Agent-->>Worker: Endringsforslag og kjøringsresultat
    Worker->>DB: Sikre sjekkpunkt og kjøringsmetadata
    Worker->>Gateway: Be om branch/PR-publisering
    Gateway->>Policy: Kontroller lease, fullmakt og gyldig bevis
    Policy-->>Gateway: Tillat / avslag / godkjenning kreves
    Gateway->>Git: Opprett branch og PR idempotent
    Git->>GH: Publiser branch og PR
    GH-->>Gateway: PR-referanse
    Gateway->>Board: Registrer PR-lenke/status
    Board->>GH: Oppdater bare eide issue-felt
    GH->>CI: Start obligatoriske kontroller
    CI-->>Hook: CI-status webhook
    Hook->>Core: Verifisert CI-resultat
    Core->>DB: Registrer resultat og korrelerte hendelser
    Core->>Policy: Vurder om leveransen oppfyller publiseringskrav
    Policy-->>Core: Verifisert / avvist / mangler kontroll
    Core->>Gateway: Be om issue-status og resultat
    Gateway->>Policy: Kontroller mandat og aktivt eierskap
    Policy-->>Gateway: Tillat / avslag
    Gateway->>Board: Oppdater eide issue-felt
    Board->>GH: Skriv status via adapter
    Core-->>Human: Status synlig i board/tidslinje
```

## Sekvens: mennesket spør en stemmeapp om innsikt

```mermaid
sequenceDiagram
    autonumber
    actor Human as Menneske
    participant Voice as ChatGPT Voice / Claude-app
    participant MCP as dev-org MCP-server
    participant API as API v1
    participant Auth as Identitet og policy
    participant Query as Status- og innsiktsspørringer
    participant DB as Persistence / PostgreSQL

    Human->>Voice: «Hvorfor står arbeidet stille?»
    Voice->>MCP: Kall relevant innsiktsverktøy
    MCP->>API: Verktøykall med brukeridentitet og avgrensning
    API->>Auth: Kontroller identitet, rolle og prosjekttilgang
    Auth-->>API: Tillat lesing / avslag
    API->>Query: Hent status, tidslinje og målinger
    Query->>DB: Les autoriserte data for prosjekt og tidsrom
    DB-->>Query: Resultater med hendelses- og målereferanser
    Query-->>API: Strukturert innsikt og kildehenvisninger
    API-->>MCP: Resultat innenfor brukerens tilgang
    MCP-->>Voice: Strukturert svar med kilder og dataperiode
    Voice-->>Human: Forklart svar med kildelenker
```

## Oppdragets livssyklus

Diagrammet viser de autoritative driftstilstandene for et oppdrag slik de er definert i del 5 av spesifikasjonen. En ventebetingelse kan for eksempel være et brukersvar, en godkjenning, en ressurs eller et eksternt resultat. Gjenopptak oppretter høyst én fortsettelse for samme hendelse og tilstand.

```mermaid
stateDiagram-v2
    direction TB
    [*] --> Klar

    Klar --> Under_arbeid: Tildel og reserver
    Under_arbeid --> Venter: Lagre betingelse og sjekkpunkt
    Venter --> Klar_til_ny_behandling: Betingelse oppfylt
    Klar_til_ny_behandling --> Under_arbeid: Opprett én fortsettelse

    Under_arbeid --> Fullført: Kriterier verifisert
    Under_arbeid --> Klar_til_ny_behandling: Avbrudd eller retry etter avstemming

    Klar --> Pauset_eller_avsluttet: Pause eller avslutt
    Under_arbeid --> Pauset_eller_avsluttet: Pause eller avslutt
    Venter --> Pauset_eller_avsluttet: Pause eller avslutt
    Klar_til_ny_behandling --> Pauset_eller_avsluttet: Pause eller avslutt
    Pauset_eller_avsluttet --> Klar: Autorisert gjenopptak
```

**Tolkning:** `Under arbeid` betyr at ett forsøk har én aktiv eier med tidsbegrenset reservasjon og fencing-token. Forsøket og reservasjonen har egne livssykluser; utløpt lease er ikke en ny oppdragstilstand. Før et nytt forsøk eller en fortsettelse startes, avstemmes usikre eksterne operasjoner og gammel eier må være stanset eller avskåret fra å skrive. Motorens samtale-ID endrer ikke oppdragstilstanden.

## Autorisasjonsflyt

Verktøyprofilen bestemmer hva klienten kan oppdage, men gir ikke i seg selv tillatelse. Hvert kall vurderes med verifisert identitet og den konkrete handlingen og ressursen. En godkjenning gjelder bare det opprinnelige, uendrede grunnlaget.

```mermaid
flowchart TD
    A[Klientkall] --> B[Verifiser aktør og kontekst]
    B --> C{Identitet gyldig?}
    C -- Nei --> X[Avslå og logg]
    C -- Ja --> D[Filtrer verktøykatalog]
    D --> E[Kall med handling og ressurs]
    E --> F[Sjekk rolle, omfang og mandat]
    F --> G{Beslutning}
    G -- Avslå --> X
    G -- Krever godkjenning --> H[Lagre avgrenset forespørsel]
    H --> I[Vent på svar]
    I --> J{Godkjent og fortsatt gyldig?}
    J -- Nei --> X
    J -- Ja --> K[Evaluer på nytt med godkjenning]
    K --> G
    G -- Tillat --> L{Ekstern sideeffekt?}
    L -- Nei --> M[Utfør lesing eller lokal handling]
    L -- Ja --> N[Gateway sjekker fullmakt, lease og bevis]
    N --> O{Kontroll bestått?}
    O -- Nei --> X
    O -- Ja --> P[Utfør via adapter og logg resultat]
```

## Rettighetsinnsyn

Rettighetsinnsyn er en lesende brukssak over identitet og policy. Egen tilgang kan inspiseres av aktøren; innsyn i andre krever særskilt fullmakt. En forhåndsvurdering viser hva policyen svarer nå, men gir ikke tillatelse til en senere utførelse.

```mermaid
flowchart TD
    A[Bruker eller agent] --> B[REST, dashboard eller MCP]
    B --> C[Verifiser identitet og kontekst]
    C --> D[Lesende tilgangsforespørsel]
    D --> E{Egen identitet?}
    E -- Ja --> G[Hent effektiv tilgang]
    E -- Nei --> F{Har innsynsfullmakt?}
    F -- Nei --> X[Avslå uten å røpe mål]
    F -- Ja --> G
    G --> H[Evaluer med gjeldende policy]
    H --> I[Samle omfang, vilkår og forklaring]
    I --> J[Logg innsyn og policyversjon]
    J --> K[Returner lesbart svar]
    K -. Forhåndsvurdering er ikke tillatelse .-> L[Faktisk handling vurderes på nytt]
```

Svaret kan vise handlingsklasser, ressursomfang, vilkår, begrunnelse, policyversjon og evalueringstid. Det viser aldri legitimasjoner eller hemmeligheter. Innsyn i andre identiteter kan ikke brukes til å omgå prosjektavgrensning.

## Lease og overlevering mellom noder

Sekvensen viser kontrollert flytting mellom workers. Den samme fencing-kontrollen gjelder når en lease utløper eller en gammel node kommer tilbake etter nettverksbrudd.

```mermaid
sequenceDiagram
    autonumber
    participant Old as Worker A / gammel eier
    participant CP as Kontrollplan
    participant Store as Persistence og operasjonsjournal
    participant Gateway as Integrasjonsgateway
    participant Artifacts as Git / artefaktlager
    participant New as Worker B / ny eier

    Old->>CP: Forny lease
    CP->>Store: Sjekk lease
    Store-->>CP: Lease fortsatt gyldig
    CP-->>Old: Fornyet
    Old->>CP: Be om stopp/checkpoint
    CP-->>Old: Stopp trygt
    Old->>Artifacts: Lagre arbeid og checkpoint
    Old->>CP: Bekreft stopp og send lenke
    CP->>Store: Avstem operasjoner
    Store-->>CP: Resultat eller ventestatus
    alt Operasjonene er trygge å overta
        CP->>Store: Bytt lease og token atomisk
        Store-->>CP: Ny eier registrert atomisk
        CP-->>New: Oppdrag, checkpoint, token
        New->>Artifacts: Hent og verifiser checkpoint
        New->>CP: Bekreft overtakelse
        CP->>Store: Sjekk eier/token
        Store-->>CP: Overtakelse gyldig
        CP-->>New: Fortsett arbeidet
        New->>Gateway: Be om sideeffekt
        Gateway->>Store: Sjekk mandat og token
        Store-->>Gateway: Tillat eller avvis
        Gateway-->>New: Resultat eller avslag
    else Ukjent utfall krever avstemming
        CP->>Store: Invalider token og sett på vent
        Store-->>CP: Ingen ny eier eller gjentatt innsending ennå
    end

    Old->>Gateway: Forsinket kall med gammelt token
    Gateway->>Store: Sjekk gammelt token
    Store-->>Gateway: Avvist, eier er erstattet
    Gateway-->>Old: Avslag, kun diagnostikk
```

## Selvforbedringssløyfen

Kandidaten kjører med separat tilstand og lavprioritert, avbrytbar kapasitet. Bare en uavhengig promoteringstjeneste kan aktivere endringer innenfor den stående rammen; ordinært arbeid fortsetter under aktiv versjon.

```mermaid
flowchart TD
    A[Driftsbevis] --> B[Endringsforslag og mål]
    B --> C[Sjekk mot ytre ramme]
    C --> D{Innenfor mandat?}
    D -- Nei eller ukjent --> E[Egen beslutningskø]
    D -- Ja --> F[Isolert kandidat]
    F --> G[Uavhengige tester]
    G --> H{Invarianter bestått?}
    H -- Nei --> I[Avvis kandidat, aktiv versjon fortsetter]
    H -- Ja --> J[Replay historiske og syntetiske data]
    J --> K[Shadow-modus]
    K --> L[Canary med sikkerhets- og flytmåling]
    L --> M{Kriterier bestått?}
    M -- Nei --> I
    M -- Ja --> N[Promoteringstjeneste]
    N --> O[Blue/green, overfør lease]
    O --> P{Helsesjekk bestått?}
    P -- Nei --> Q[Rollback, gammel versjon fortsetter]
    P -- Ja --> R[Aktiver ny versjon og logg resultat]
    R --> A
```

## Diagramomfang og kontrakter som gjenstår

Diagrammene viser utvalgte normalflyter. Retry, utløpt lease, dupliserte webhooker, CI-avstemming og uavklarte eksterne kall følger de normative reglene i del 3.2 og 5–7 av [spesifikasjonen](../../dev-org-spesifikasjon.md); de skal ikke kopieres inn som parallelle regler her.

Arkitekturbeslutningen for eksterne mutasjoner er lukket: organisasjonskjernen eier brukstilfellet og ber gatewayen utføre endringen; bare gatewayen kaller muterende adapteroperasjoner. Sekvensen for GitHub-sak viser denne flyten.

Følgende versjonerte kontraktartefakter skal ferdigstilles før den tilsvarende adapteren implementeres. Spekken fastsetter semantikken; rutene, serialiserte skjemaene og adapterspesifikke konfigurasjonsverdiene hører hjemme i disse kontraktene.

| Kontraktartefakt | Allerede fastsatt | Må konkretiseres før |
|---|---|---|
| Worker API | Claim, lease/fencing, sjekkpunkt, resultat, stopp og overleveringsregler i del 5 og 7. | Worker-adapteren: operasjoner, payloads, feil, autentisering, idempotens og retry-respons. |
| `Task`, `Attempt` og `Reservation` | Oppdrag, forsøk og reservasjon er separate konsepter; livssyklus og eierskapsregler er beskrevet i del 5. | Persistence- og worker-adapter: versjonerte felt, ID-er, relasjoner og migreringsregler. De må ikke slås sammen til én statusmaskin. |
| Sjekkpunkt og artefaktreferanse | Påkrevd sjekkpunktinnhold, integritetskontroll og flytteprinsipper i del 5 og 7. | Artefakt-/worker-adapter: referanseskjema, opplasting/nedlasting, retention og feilhåndtering. |
| MCP-verktøykatalog | Versjonerte grupper, tilgangsregler og brukstilfeller er beskrevet i del 3.2 og 4. | MCP-adapter: eksakte verktøynavn, input/output-skjema, feil og paginering der det trengs. |
| Boardstatusmapping | Felles statuser er `Ready`, `In progress`, `Blocked`, `In review` og `Done`; ukjent status stanser automatisk tildeling. | Prosjektoppsett/boardadapter: konkrete GitHub-felt-ID-er og alternativ-ID-er, validert mot valgt prosjekt før aktivering. |

Tilgjengelighet for egendefinerte MCP-servere i en bestemt stemmeapp er en klient-/leverandørbegrensning, ikke en åpen arkitekturbeslutning. Den er omtalt i del 4; andre kompatible MCP-klienter bruker samme inngang.
