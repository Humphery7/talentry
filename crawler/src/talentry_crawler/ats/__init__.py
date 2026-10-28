"""Talk to external ATS APIs. One file per provider. No database writes here."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx

from talentry_crawler.models import Board, Job

from . import (
    accenture,
    almacareer,
    amazon,
    ashby,
    bamboohr,
    beehire,
    beisen,
    brassring,
    bytedance,
    cnstaff,
    comeet,
    cornerstone,
    curately,
    deel,
    dvinci,
    earcu,
    fenbi,
    gem,
    greenhouse,
    hibob,
    hirehive,
    hireology,
    jarvi,
    job51,
    keka,
    lever,
    manatal,
    nowhiring,
    paynet,
    personio,
    pinpoint,
    recruitee,
    recruiter_co_kr,
    seamlesshiring,
    talentreef,
    traffit,
    turbohire,
    universia,
    wecruit,
    welcometothejungle,
    woowa,
)

DiscoverFn = Callable[[Board, httpx.AsyncClient], Awaitable[list[Job]]]

# Register every supported provider here. Adding an adapter = new file + one line.
REGISTRY: dict[str, DiscoverFn] = {
    "accenture": accenture.discover,
    "almacareer": almacareer.discover,
    "beisen": beisen.discover,
    "hireology": hireology.discover,
    "wecruit": wecruit.discover,
    "brassring": brassring.discover,
    "bytedance": bytedance.discover,
    "dvinci": dvinci.discover,
    "earcu": earcu.discover,
    "fenbi": fenbi.discover,
    "greenhouse": greenhouse.discover,
    "ashby": ashby.discover,
    "lever": lever.discover,
    "pinpoint": pinpoint.discover,
    "recruitee": recruitee.discover,
    "gem": gem.discover,
    "personio": personio.discover,
    "deel": deel.discover,
    "hirehive": hirehive.discover,
    "traffit": traffit.discover,
    "manatal": manatal.discover,
    "bamboohr": bamboohr.discover,
    "hibob": hibob.discover,
    "recruiter_co_kr": recruiter_co_kr.discover,
    "talentreef": talentreef.discover,
    "cornerstone": cornerstone.discover,
    "beehire": beehire.discover,
    "seamlesshiring": seamlesshiring.discover,
    "cnstaff": cnstaff.discover,
    "paynet": paynet.discover,
    "universia": universia.discover,
    "comeet": comeet.discover,
    "jarvi": jarvi.discover,
    "keka": keka.discover,
    "nowhiring": nowhiring.discover,
    "turbohire": turbohire.discover,
    "amazon": amazon.discover,
    "curately": curately.discover,
    "job51": job51.discover,
    "welcometothejungle": welcometothejungle.discover,
    "woowa": woowa.discover,
}


def get_discoverer(monitor_type: str) -> DiscoverFn:
    try:
        return REGISTRY[monitor_type]
    except KeyError as exc:
        raise KeyError(
            f"No ATS adapter for {monitor_type!r}. Available: {sorted(REGISTRY)}"
        ) from exc
