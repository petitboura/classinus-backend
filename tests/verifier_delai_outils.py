import ast, asyncio, logging, os, time, threading
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core", "mcp_tools.py"), encoding="utf-8").read()
arbre = ast.parse(src)
voulus = {"_entier_env","DELAI_OUTIL_DEFAUT_SECONDES","DELAI_OUTIL_MAX_SECONDES","PARAMETRE_DELAI_OUTIL","_AppelAnnule","_delai_demande","_schema_avec_delai","_appeler_avec_delai_et_arret","appeler_outil"}
noeuds=[]
for n in arbre.body:
    nom = getattr(n,"name",None) or (n.targets[0].id if isinstance(n,ast.Assign) else None)
    if nom in voulus: noeuds.append(n)
ns={"asyncio":asyncio,"logging":logging,"os":os,"time":time}
# faux serveur MCP : dort `duree` secondes puis répond
etat={"duree":0.1,"args":None}
async def faux(url,nom,arguments,headers=None):
    etat["args"]=dict(arguments)
    await asyncio.sleep(etat["duree"]); return "ok"
ns["_appeler_outil_async"]=faux
ns["_message_erreur_technique_outil"]=lambda n:"erreur technique"
exec(compile(ast.Module(body=noeuds,type_ignores=[]),"mcp_tools_extrait","exec"),ns)
os.environ.pop("DELAI_OUTIL_DEFAUT_SECONDES",None)
ao=ns["appeler_outil"]; table={"x":{"url":"u"}}
# la limite est de 60 s par défaut : on la baisse pour tester vite
ns["DELAI_OUTIL_DEFAUT_SECONDES"]=1; ns["DELAI_OUTIL_MAX_SECONDES"]=3
class Arret:
    def __init__(s): s.e=threading.Event()
    def est_demande(s): return s.e.is_set()
print("1 rapide        :", ao("x",{"a":1},table))
print("  args transmis :", etat["args"])
etat["duree"]=5
t=time.time(); r=ao("x",{},table); print("2 trop long     :", round(time.time()-t,1),"s |", r[:60])
t=time.time(); r=ao("x",{"delai_max_secondes":99},table); print("3 délai demandé 99 -> plafonné à 3 s :", round(time.time()-t,1),"s")
etat["duree"]=2
print("4 délai 3 suffit:", ao("x",{"delai_max_secondes":3},table), "| args transmis:", etat["args"])
a=Arret(); threading.Timer(0.5,a.e.set).start(); etat["duree"]=5
t=time.time(); r=ao("x",{},table,arret=a); print("5 Arrêter       :", round(time.time()-t,1),"s |", r[:50])
print("6 clamp         :", ns["_delai_demande"](None), ns["_delai_demande"]("abc"), ns["_delai_demande"](0), ns["_delai_demande"](2), ns["_delai_demande"](50))
s={"type":"object","properties":{"q":{"type":"string"}}}
s2=ns["_schema_avec_delai"](s); print("7 schéma        :", list(s2["properties"]), "| original intact:", list(s["properties"]))
print("  sans propriétés:", list(ns["_schema_avec_delai"]({"type":"object"})["properties"]), "| non objet:", ns["_schema_avec_delai"]({"type":"string"}))
