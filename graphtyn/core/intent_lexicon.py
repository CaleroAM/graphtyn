"""Concept cues for each intent, in the six languages Graphtyn is asked in.

Markers in `intent_classifier` are single words; these cues are the ways a question
asks for each kind of evidence ("who directly calls", "se verían afectados", "wird
... eingehängt"). A cue weighs more than an incidental marker: "save" or "query" in
a question about a lifecycle must not make it a persistence question.

Written from the meaning of each intent, not from benchmark questions: the held-out
sets that measure the classifier are generated and labelled by another model.
"""
from __future__ import annotations

import re

CUE_WEIGHT = 2

# An adverb may sit between the subject and the verb: "who directly calls".
_ADVERB = r"(?:\s+(?:\w+mente|directly|currently|still|actually|direkt|directement|encore|diretamente|direttamente|ainda|todav[ií]a|a[uú]n))?"

_IMPACT = (
    # Who uses it.
    rf"\b(?:qui[eé]n(?:es)?|who|quem|qui|wer|chi){_ADVERB}\s+(?:\w+\s+)?(?:llama|llaman|usa|usan|utiliza|utilizan|invoca|invocan|"
    rf"consume|consumen|depende|dependen|calls?|uses?|invokes?|consumes?|depends|imports?|chama|chamam|usam|consomem|"
    rf"appelle|appellent|utilise|utilisent|consomme|ruft|rufen|verwendet|verwenden|benutzt|nutzt|importiert|chiama|chiamano|"
    rf"utilizzano|usano|invocano|consumano|dipende|dipendono|riferimento|referencia|refer[eê]ncia|r[ée]f[ée]rence|referenziert|"
    rf"references?|refers)\b",
    # "what classes ... call it", "qué funciones lo están llamando", "quels fichiers appellent".
    r"\b(?:what|which|qu[eé]|quais|quels?|quelles?|welche[nrs]?|quali)\s+(?:other\s+|otr[oa]s\s+|outr[oa]s\s+|autres\s+|andere[nrs]?\s+|altr[ei]\s+)?"
    r"(?:classes|clases|classi|klassen|functions|funciones|fun[cç][oõ]es|fonctions|funktionen|funzioni|methods|m[eé]todos|"
    r"m[ée]thodes|methoden|metodi|modules|m[oó]dulos|module|moduli|files|archivos|arquivos|fichiers|dateien|file|"
    r"components|componentes|composants|komponenten|componenti|controllers|controladores|contr[oô]leurs|controller|"
    r"services|servicios|servi[cç]os|dienste|servizi|parts|partes|parties|teile|parti|code|c[oó]digo)\b[^?]*?"
    r"\b(?:call|calls|use|uses|consume|consumes|import|imports|reference|references|llama|llaman|llamando|usa|usan|usando|"
    r"utiliza|utilizan|utilizando|importa|importan|consume|consumen|referencian|chamam|chamando|usam|consomem|importam|"
    r"referenciam|appellent|utilisent|importent|consomment|r[ée]f[ée]rencent|rufen|verwenden|nutzen|benutzen|importieren|"
    r"referenzieren|chiamano|richiamano|usano|utilizzano|importano|consumano)\b",
    r"\b(?:lo|la|los|las)\s+(?:est[aá]n?\s+|siguen\s+)?(?:llama|llaman|llamando|usa|usan|usando|utiliza|utilizan|utilizando|invoca|invocan|invocando)\b",
    r"\b(?:callers?|consumers?|dependents?|llamadores|consumidores|dependientes|chamadores|consumidores|appelants|"
    r"consommateurs|aufrufer|verbraucher|chiamanti|consumatori|utilizzatori)\b",
    # What breaks or is affected.
    r"\b(?:break|breaks|broken|would break|will break|stop (?:working|compiling)|affected|impacted|affects|impacts|"
    r"rompe|romper[ií]a|romper[aá]n?|romp(?:en|er)|afectad[oa]s?|afectar[ií]a|afectan|impactad[oa]s?|impactar[ií]a|"
    r"dejar[ií]an? de (?:funcionar|compilar)|van a dejar de|"
    r"quebra|quebrar|quebraria|afetad[oa]s?|afetaria|impactad[oa]s?|parar de funcionar|deixar(?:ia|iam)? de (?:funcionar|compilar)|"
    r"cass(?:e|er|era|eront|ent)|impact[ée]e?s?|affect[ée]e?s?|cesser de|"
    r"bricht|brechen|kaputt|betroffen|beeinflusst|beeintr[aä]chtigt|auswirkungen?|"
    r"si rompe|rompe(?:rebbe|ranno)?|impattat[oi]|influenzat[oi]|risent(?:e|ono|iranno|irebbe)|conseguenze|quebram|quebrariam|"
    r"would fail|will fail|fallar[ií]an|fallar[aá]n?|falhar[aã]o|falhariam|[ée]choueront|[ée]choueraient|fallirebbero|falliranno|"
    r"schlagen fehl|fehlschlagen)\b",
    r"\b(?:depende[nm]? (?:directamente |diretamente )?(?:de|da|do|das|dos|disso|dela|dele)|depend(?:s|ent)? (?:directly )?on|"
    r"d[eé]pend(?:ent)? (?:directement )?(?:de|du|des)|"
    r"h[aä]ngt\b[^?]*\bab|abh[aä]ngig|dipend(?:e|ono) (?:direttamente )?da)\b",
    r"\bgreif(?:t|en)\b[^?]*\bzu\b|\brufen?\b[^?]*\bauf\b",
)

_TESTS = (
    r"\b(?:tests?|testing|tested|unit-tested|spec|specs|rspec|minitest|jest|pytest|junit|phpunit|mocha|vitest|"
    r"pruebas?|probad[oa]|teste|testes|testad[oa]|testé|testée|getestet|testet|testato|testati|collaudo|"
    r"fixtures?|mocks?|mocked|mockea|mockad[oa]|gemockt|stubs?|doubles?|cobertura|coverage|couverture|abdeckung|copertura)\b",
    r"@\w*test\b|\b\w+_(?:test|spec)\b|\w+\.(?:spec|test)\.\w+|\b\w{3,}tests\b|\btestdatei\w*|\btestf[aä]ll\w*",
)

_PERSISTENCE = (
    r"\b(?:tables?|tablas?|tabelas?|tabelle|tabella|tabellen|schema|schemas|esquemas?|sch[ée]ma|migrations?|migraci[oó]n|"
    r"migraciones|migra[cç][aã]o|migra[cç][oõ]es|migrazion[ei]|migrations\w+|orm|dbcontext|dbset|"
    r"database|databases|base de datos|bases de datos|banco de dados|base de donn[ée]es|datenbank|disk|disco|disque|platte|festplatte|"
    r"primary keys?|foreign keys?|clave primaria|"
    r"chave prim[aá]ria|cl[ée] primaire|prim[aä]rschl[uü]ssel|chiave primaria|"
    r"wal|checkpoint|on disk|en disco|no disco|sur disque|auf (?:der )?(?:platte|festplatte)|su disco)\b",
    r"\b(?:stored|stores|storage|store data|persisted|persists|almacena(?:n|do|da|miento)?|se guarda(?:n)?|"
    r"armazena(?:d[oa]s?|m|mento)?|stock(?:e|é|ée|és|ent|age)|speicher(?:t|n|ung)?|\w+speicher|gespeichert|abgelegt|"
    r"memorizzat[oi]|salvat[oi] (?:su|nel|nella|in)|archiviat[oi])\b",
)

# Words that often, not always, mean storage: a domain entity or a serialized contract.
_PERSISTENCE_WEAK = (
    r"\b(?:entit(?:y|ies)|entidad(?:es)?|entidades?|entit[ée]s?|entit[aä]t(?:en)?|entit[aà]|modell?s?|modelos?|mod[eè]les?|"
    r"modelli|collection|collections|colecci[oó]n|cole[cç][aã]o|collezione|indexes|indices|índices|serializ\w+|"
    r"serialis\w+|deserializ\w+)\b",
)

_BINDINGS = (
    r"\b(?:inject(?:s|ed|ion|able)?|dependency injection|inyect(?:a|an|ado|ada|ar)|inyecci[oó]n|inje(?:ta|tam|tad[oa]|tar|[cç][aã]o)|"
    r"inject[ée]e?s?|injecter|injizier(?:t|en)|injektion|abh[aä]ngigkeitsinjektion|iniett(?:at[oa]|are|a|ano)|iniezione)\b",
    r"\b(?:service container|container de servi[cç]os|contenedor de servicios|conteneur de services|ioc|di container|"
    r"service providers?|serviceprovider|proveedor de servicios|provedor de servi[cç]os|fournisseur de services|"
    r"beans?|autowir\w*|wire[sd]?|wiring|cablead[oa]|bound to|binds?|bindings?|vincula(?:da|do|r)?|li[ée]e? (?:à|a)|"
    r"gebunden|legat[oa] (?:a|al)|singleton|transient|scoped|qualifier|providers|verdrahtung|verdrahtet|atrelad[oa]s?)\b",
    r"@(?:configuration|module|bean|qualifier|inject|autowired|injectable|component|service)\b|\bapp_guard\b",
    # Registering or mounting a middleware, guard, plugin or service.
    r"\b(?:regist(?:er|ered|ers|ra|rados?|radas?|ran|rar|riert|riert[en]?|rat[oiae]|r[ée]e?s?)|enregistr\w*|mount(?:ed)?|montad[oa]|mont[ée]e?|"
    r"montat[oa]|eingeh[aä]ngt|einh[aä]ngen|plugged|plugad[oa]s?|branch[ée]e?s?|agganciat[oa]|aggancia|rattach[ée]e?s?|"
    r"instal\w*|install\w*|adicionad[oa]s?|añadid[oa]s?|agregad[oa]s?|ajout[ée]e?s?|hinzugef[uü]gt|aggiunt[oi])\b"
    r"[^?]*\b(?:middlewares?|guards?|plugins?|services?|providers?|extensions?|interceptors?|filters?|filtros?|filtres?|"
    r"webhooks?|hooks?|listeners?|handlers? globales?|global)\b",
    r"\b(?:middlewares?|guards?|plugins?|interceptors?|webhooks?|listeners?|filters?)\b[^?]*\b(?:regist\w*|mount\w*|montad\w*|"
    r"mont[ée]\w*|eingeh[aä]ngt|plug\w*|aggancia\w*|rattach\w*|atrelad\w*|adicionad\w*|añadid\w*|agregad\w*|ajout\w*|"
    r"hinzugef\w*|aggiunt\w*|instal\w*|global(?:mente|ly|ement)?)\b",
)

_OVERVIEW_WEAK = (
    r"\b(?:structured|organi[sz]ed|se encarga|responsible for|respons[aá]vel|responsable de|zust[aä]ndig|si occupa|"
    r"purpose|prop[oó]sito|objetivo general|scopo|zweck|objectif|but (?:de|du)|entry point|punto de entrada|"
    r"ponto de entrada|point d'entr[ée]e|einstiegspunkt|punto (?:di|d')\s?ingresso|tech stack|stack)\b",
)

_OVERVIEW = (
    r"\b(?:se (?:estructura|organiza|divide)n?|est[aá] (?:estructurad|organizad)[oa]|(?:is|are) (?:structured|organi[sz]ed|split)|"
    r"organisiert|gegliedert|aufgebaut|organis[ée]e?|structur[ée]e?|organizzat[oa]|strutturat[oa]|suddivis[oa]|"
    r"subsystems?|subsistemas?|sous-syst[eè]mes?|subsysteme?|sottosistemi|componentes fundamentales|componentes fundamentais|"
    r"composants fondamentaux|grundlegende komponenten|componenti fondamentali|"
    r"high-level|alto nivel|alto n[ií]vel|haut niveau|[uü]bersicht|überblick|panoramica|panorama|presentaci[oó]n general|"
    r"pr[ée]sentation|architecture|arquitectura|arquitetura|architektur|architettura|layout|"
    r"estructura (?:principal|general)|estrutura|organizaci[oó]n|organiza[cç][aã]o|organisation|organizzazione|"
    r"gesamtstruktur|struktur|struttura|structure|d[ée]coup[ée]|gegliedert|layers|capas|camadas|couches|schichten|livelli|"
    r"building blocks|bausteine|hauptkomponenten|main components|componentes principales|componentes principais|"
    r"composants principaux|componenti principali|core modules|m[oó]dulos principales|m[oó]dulos principais|"
    r"modules principaux|moduli principali|starting point|punto de partida|ponto de partida|point de d[ée]part|"
    r"startpunkt|punto di partenza|what (?:is|does) this (?:repo|project|codebase))\b",
    r"\b(?:carpetas?|folders?|directories|directorios|pastas|r[ée]pertoires|verzeichnisse|cartelle)\b",
)

_FLOW = (
    # Asking for the trace itself outweighs a stage that stores data or reads a folder.
    r"\b(?:traza|trazar|traces?|tracing|tra[cç]ar?|retrace|retracer|verfolge|nachverfolgen|traccia|tracciare|rastrea|flujo|flow|fluxo|"
    r"ablauf|flusso)\b",
    r"\b(?:lifecycle|life cycle|ciclo de vida|cycle de vie|lebenszyklus|ciclo di vita)\b",
    r"\b(?:step by step|paso a paso|passo a passo|[ée]tape par [ée]tape|schritt f[uü]r schritt|passo dopo passo|"
    r"in what order|en qu[eé] orden|em que ordem|dans quel ordre|in welcher reihenfolge|in che ordine)\b",
    r"\b(?:what happens|qu[eé] (?:pasa|sucede|ocurre)|o que acontece|que se passe|was passiert|cosa succede)\b",
)

CUES = {intent: tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
        for intent, patterns in (("impact", _IMPACT), ("tests", _TESTS), ("persistence", _PERSISTENCE),
                                 ("persistence_weak", _PERSISTENCE_WEAK), ("bindings", _BINDINGS), ("overview", _OVERVIEW),
                                 ("overview_weak", _OVERVIEW_WEAK), ("flow", _FLOW))}
# A weak cue counts as much as a single-word marker.
_WEIGHTS = {"persistence_weak": 1}


def cue_scores(text: str) -> dict[str, int]:
    """The weight of each concept pattern of an intent the text matches."""
    return {intent: _WEIGHTS.get(intent, CUE_WEIGHT) * sum(bool(pattern.search(text)) for pattern in patterns)
            for intent, patterns in CUES.items()}


def asks_impact(text: str) -> bool:
    return any(pattern.search(text) for pattern in CUES["impact"])
