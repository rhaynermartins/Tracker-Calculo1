import argparse
import csv
import math
import os
import re
import statistics
import unicodedata
from typing import Dict, List, Optional, Tuple

# Remove acentos e padroniza texto para facilitar a identificação das colunas.
def normalizar_texto(txt: str) -> str:
    txt = str(txt).strip().lower()
    txt = unicodedata.normalize("NFKD", txt)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return txt

# Converte valores numéricos vindos do Tracker.
def converter_numero(valor: str) -> Optional[float]:

    if valor is None:
        return None

    texto = str(valor).strip().replace("\ufeff", "")
    if texto == "":
        return None

    # Remove espaços e unidades comuns, mantendo números, sinais, vírgula, ponto e notação científica.
    texto = texto.replace(" ", "")
    texto = re.sub(r"[^0-9,\.\-+eE]", "", texto)

    if texto in {"", "+", "-", ".", ","}:
        return None

    # Caso brasileiro: 1,23 -> 1.23
    # Caso com milhar: 1.234,56 -> 1234.56
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None

# Tenta descobrir se o CSV usa ponto e vírgula, vírgula ou tabulação.
def detectar_delimitador(linhas: List[str]) -> str:
    amostra = "\n".join(linhas[:15])
    candidatos = [";", "\t", ","]

    try:
        dialect = csv.Sniffer().sniff(amostra, delimiters=";\t,")
        return dialect.delimiter
    except Exception:
        pass

    # Heurística simples: escolhe o separador mais frequente nas primeiras linhas.
    contagens = {d: sum(l.count(d) for l in linhas[:15]) for d in candidatos}
    return max(contagens, key=contagens.get)


def localizar_colunas(cabecalho: List[str]) -> Tuple[Optional[int], Optional[int]]:
    """Identifica as colunas de tempo e posição pelo nome do cabeçalho."""
    nomes = [normalizar_texto(c) for c in cabecalho]

    tempo_idx = None
    pos_idx = None

    for i, nome in enumerate(nomes):
        if nome in {"t", "time", "tempo"} or "tempo" in nome or "time" in nome:
            tempo_idx = i
            break

    # Preferência para posição/x. No Tracker, muitas vezes a posição horizontal vem como x.
    for i, nome in enumerate(nomes):
        if i == tempo_idx:
            continue
        if (
            "posicao" in nome
            or "position" in nome
            or nome in {"x", "x(m)", "xcm", "xm", "xpix"}
            or nome.startswith("x ")
        ):
            pos_idx = i
            break

    return tempo_idx, pos_idx

# Lê o CSV exportado pelo Tracker e retorna uma lista de pares (tempo, posição).
def ler_csv_tracker(caminho: str) -> Tuple[List[Tuple[float, float]], Dict[str, str]]:
 
    with open(caminho, "r", encoding="utf-8-sig", errors="replace") as f:
        linhas = [l.rstrip("\n") for l in f if l.strip()]

    if not linhas:
        raise ValueError("Arquivo vazio.")

    delimitador = detectar_delimitador(linhas)
    leitor = csv.reader(linhas, delimiter=delimitador)
    linhas_csv = [list(l) for l in leitor]

    tempo_idx = None
    pos_idx = None
    inicio_dados = 0
    cabecalho_usado = None

    # Procura um cabeçalho provável.
    for i, linha in enumerate(linhas_csv[:30]):
        t_idx, x_idx = localizar_colunas(linha)
        if t_idx is not None and x_idx is not None:
            tempo_idx, pos_idx = t_idx, x_idx
            inicio_dados = i + 1
            cabecalho_usado = linha
            break

    dados: List[Tuple[float, float]] = []

    if tempo_idx is not None and pos_idx is not None:
        for linha in linhas_csv[inicio_dados:]:
            if max(tempo_idx, pos_idx) >= len(linha):
                continue
            tempo = converter_numero(linha[tempo_idx])
            posicao = converter_numero(linha[pos_idx])
            if tempo is not None and posicao is not None:
                dados.append((tempo, posicao))
    else:
        # Sem cabeçalho claro: usa as duas primeiras colunas numéricas de cada linha.
        for linha in linhas_csv:
            numeros = [converter_numero(c) for c in linha]
            numeros = [n for n in numeros if n is not None]
            if len(numeros) >= 2:
                dados.append((numeros[0], numeros[1]))

    if len(dados) < 2:
        raise ValueError(
            "Não foi possível encontrar dados suficientes de tempo e posição. "
            "Confira se o arquivo tem colunas de Tempo e Posição/x."
        )

    # Remove tempos duplicados e ordena pelo tempo.
    vistos = set()
    dados_limpos = []
    for t, x in dados:
        chave = round(t, 12)
        if chave not in vistos:
            dados_limpos.append((t, x))
            vistos.add(chave)

    dados_limpos.sort(key=lambda p: p[0])

    info = {
        "delimitador": "TAB" if delimitador == "\t" else delimitador,
        "cabecalho": str(cabecalho_usado) if cabecalho_usado else "não identificado",
    }
    return dados_limpos, info



# Cálculos físicos/matemáticos


# Retorna o fator para converter a posição para metros.
def fator_unidade(posicoes: List[float], unidade: str) -> float:
    unidade = unidade.lower()
    if unidade == "m":
        return 1.0
    if unidade == "cm":
        return 0.01
    if unidade == "mm":
        return 0.001
    if unidade == "auto":
        # Para uma pista de cerca de 2,20 m, valores como 50, 100, 150 indicam cm.
        mediana_abs = statistics.median(abs(x) for x in posicoes)
        if mediana_abs > 10:
            return 0.01
        return 1.0
    raise ValueError("Unidade inválida. Use: m, cm, mm ou auto.")

# Calcula velocidade média entre dois pontos: Δs/Δt.
def velocidade_media(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    t1, x1 = p1
    t2, x2 = p2
    if t2 == t1:
        raise ValueError("Dois pontos possuem o mesmo tempo; não é possível dividir por zero.")
    return (x2 - x1) / (t2 - t1)

# Monta intervalos com um ponto antes e um ponto depois de P.
def montar_intervalos_em_torno_de_p(
    dados: List[Tuple[float, float]], ponto_p: float, max_intervalos: int = 8
) -> List[Dict[str, float]]:
  
    antes = []
    depois = []

    for t, x in dados:
        if x < ponto_p:
            antes.append((t, x))
        elif x > ponto_p:
            depois.append((t, x))

    antes.sort(key=lambda p: abs(p[1] - ponto_p))
    depois.sort(key=lambda p: abs(p[1] - ponto_p))

    qtd = min(len(antes), len(depois), max_intervalos)
    intervalos = []

    for i in range(qtd):
        p_esq = antes[i]
        p_dir = depois[i]

        # Mantém a ordem temporal correta.
        if p_esq[0] <= p_dir[0]:
            p1, p2 = p_esq, p_dir
        else:
            p1, p2 = p_dir, p_esq

        t1, x1 = p1
        t2, x2 = p2
        v = velocidade_media(p1, p2)

        intervalos.append(
            {
                "ordem": i + 1,
                "t1": t1,
                "x1": x1,
                "t2": t2,
                "x2": x2,
                "delta_t": t2 - t1,
                "delta_x": x2 - x1,
                "distancia_media_ate_p": (abs(x1 - ponto_p) + abs(x2 - ponto_p)) / 2,
                "velocidade_media_ms": v,
                "velocidade_media_kmh": v * 3.6,
            }
        )

    intervalos.sort(key=lambda item: item["distancia_media_ate_p"])
    return intervalos

# Estima a velocidade instantânea pela inclinação de uma reta ajustada nos pontos mais próximos de P.
def regressao_linear_local(
    dados: List[Tuple[float, float]], ponto_p: float, qtd_pontos: int = 7
) -> Optional[Dict[str, float]]:
   
    if len(dados) < 3:
        return None

    pontos = sorted(dados, key=lambda p: abs(p[1] - ponto_p))[: min(qtd_pontos, len(dados))]
    if len(pontos) < 3:
        return None

    tempos = [p[0] for p in pontos]
    posicoes = [p[1] for p in pontos]

    media_t = statistics.mean(tempos)
    media_x = statistics.mean(posicoes)

    soma_tt = sum((t - media_t) ** 2 for t in tempos)
    if soma_tt == 0:
        return None

    soma_tx = sum((t - media_t) * (x - media_x) for t, x in pontos)
    a = soma_tx / soma_tt
    b = media_x - a * media_t

    return {
        "velocidade_ms": a,
        "velocidade_kmh": a * 3.6,
        "intercepto": b,
        "qtd_pontos": len(pontos),
        "menor_distancia_p": min(abs(x - ponto_p) for _, x in pontos),
        "maior_distancia_p": max(abs(x - ponto_p) for _, x in pontos),
    }

# Calcula, por interpolação linear, o instante aproximado em que o carrinho passa por P.
def tempo_aproximado_em_p(dados: List[Tuple[float, float]], ponto_p: float) -> Optional[float]:
    for (t1, x1), (t2, x2) in zip(dados, dados[1:]):
        if x1 == ponto_p:
            return t1
        if (x1 - ponto_p) * (x2 - ponto_p) <= 0 and x1 != x2:
            frac = (ponto_p - x1) / (x2 - x1)
            return t1 + frac * (t2 - t1)
    return None


def analisar_arquivo(caminho: str, ponto_p_original: float, unidade: str, max_intervalos: int) -> Dict:
    dados_brutos, info = ler_csv_tracker(caminho)
    posicoes_brutas = [x for _, x in dados_brutos]
    fator = fator_unidade(posicoes_brutas, unidade)

    dados = [(t, x * fator) for t, x in dados_brutos]
    ponto_p = ponto_p_original * fator

    intervalos = montar_intervalos_em_torno_de_p(dados, ponto_p, max_intervalos=max_intervalos)
    regressao = regressao_linear_local(dados, ponto_p)
    tempo_p = tempo_aproximado_em_p(dados, ponto_p)

    if regressao is not None:
        estimativa_ms = regressao["velocidade_ms"]
        metodo = "regressão linear local com os pontos mais próximos de P"
    elif intervalos:
        estimativa_ms = intervalos[0]["velocidade_media_ms"]
        metodo = "velocidade média no menor intervalo em torno de P"
    else:
        raise ValueError(
            "Não há pontos suficientes antes e depois de P. "
            "Verifique o valor de P ou o recorte dos dados."
        )

    return {
        "arquivo": caminho,
        "info": info,
        "unidade_entrada": unidade,
        "fator_unidade": fator,
        "ponto_p_m": ponto_p,
        "qtd_pontos": len(dados),
        "tempo_p": tempo_p,
        "intervalos": intervalos,
        "regressao": regressao,
        "estimativa_ms": estimativa_ms,
        "estimativa_kmh": estimativa_ms * 3.6,
        "metodo": metodo,
    }



# Saída e apresentação


def imprimir_resultado(resultado: Dict) -> None:
    nome = os.path.basename(resultado["arquivo"])
    print("\n" + "=" * 72)
    print(f"Arquivo analisado: {nome}")
    print(f"Quantidade de pontos lidos: {resultado['qtd_pontos']}")
    print(f"Ponto de referência P: {resultado['ponto_p_m']:.6f} m")
    print(f"Cabeçalho identificado: {resultado['info']['cabecalho']}")
    print(f"Delimitador identificado: {resultado['info']['delimitador']}")

    if resultado["tempo_p"] is not None:
        print(f"Instante aproximado em que o carrinho passa por P: {resultado['tempo_p']:.6f} s")

    print("\nVelocidades médias em intervalos ao redor de P:")
    print("ordem | x1(m)     t1(s)     x2(m)     t2(s)     Δx(m)     Δt(s)     v(m/s)    v(km/h)")
    print("-" * 94)

    for item in resultado["intervalos"]:
        print(
            f"{item['ordem']:>5} | "
            f"{item['x1']:>8.4f}  {item['t1']:>8.4f}  "
            f"{item['x2']:>8.4f}  {item['t2']:>8.4f}  "
            f"{item['delta_x']:>8.4f}  {item['delta_t']:>8.4f}  "
            f"{item['velocidade_media_ms']:>8.4f}  {item['velocidade_media_kmh']:>8.4f}"
        )

    if resultado["regressao"] is not None:
        reg = resultado["regressao"]
        print("\nEstimativa por regressão linear local:")
        print(f"Pontos usados: {reg['qtd_pontos']}")
        print(f"Velocidade estimada: {reg['velocidade_ms']:.6f} m/s = {reg['velocidade_kmh']:.6f} km/h")

    print("\nResultado final:")
    print(f"Método adotado: {resultado['metodo']}")
    print(
        "A velocidade instantânea do veículo ao passar pelo ponto P é aproximadamente "
        f"{resultado['estimativa_ms']:.4f} m/s, ou {resultado['estimativa_kmh']:.4f} km/h."
    )

# Salva a tabela de velocidades médias e a estimativa final em CSV.
def salvar_resultados_csv(resultados: List[Dict], caminho_saida: str) -> None:

    with open(caminho_saida, "w", newline="", encoding="utf-8") as f:
        campos = [
            "arquivo",
            "ponto_p_m",
            "ordem_intervalo",
            "x1_m",
            "t1_s",
            "x2_m",
            "t2_s",
            "delta_x_m",
            "delta_t_s",
            "velocidade_media_m_s",
            "velocidade_media_km_h",
            "velocidade_final_m_s",
            "velocidade_final_km_h",
            "metodo_final",
        ]
        escritor = csv.DictWriter(f, fieldnames=campos)
        escritor.writeheader()

        for res in resultados:
            for item in res["intervalos"]:
                escritor.writerow(
                    {
                        "arquivo": os.path.basename(res["arquivo"]),
                        "ponto_p_m": f"{res['ponto_p_m']:.8f}",
                        "ordem_intervalo": item["ordem"],
                        "x1_m": f"{item['x1']:.8f}",
                        "t1_s": f"{item['t1']:.8f}",
                        "x2_m": f"{item['x2']:.8f}",
                        "t2_s": f"{item['t2']:.8f}",
                        "delta_x_m": f"{item['delta_x']:.8f}",
                        "delta_t_s": f"{item['delta_t']:.8f}",
                        "velocidade_media_m_s": f"{item['velocidade_media_ms']:.8f}",
                        "velocidade_media_km_h": f"{item['velocidade_media_kmh']:.8f}",
                        "velocidade_final_m_s": f"{res['estimativa_ms']:.8f}",
                        "velocidade_final_km_h": f"{res['estimativa_kmh']:.8f}",
                        "metodo_final": res["metodo"],
                    }
                )



# Programa principal


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analisa CSVs do Tracker e estima a velocidade instantânea no ponto P."
    )
    parser.add_argument(
        "arquivos",
        nargs="+",
        help="Um ou mais arquivos CSV exportados pelo Tracker.",
    )
    parser.add_argument(
        "--ponto-p",
        type=float,
        default=None,
        help="Valor da posição do ponto P na mesma unidade do CSV. Ex.: 1.10 se estiver em metros; 100 se estiver em centímetros.",
    )
    parser.add_argument(
        "--unidade-pos",
        choices=["auto", "m", "cm", "mm"],
        default="auto",
        help="Unidade da coluna de posição no CSV. Padrão: auto.",
    )
    parser.add_argument(
        "--max-intervalos",
        type=int,
        default=8,
        help="Quantidade máxima de intervalos de velocidade média a mostrar.",
    )
    parser.add_argument(
        "--saida",
        default="resultados_velocidade.csv",
        help="Nome do arquivo CSV de saída com os resultados.",
    )

    args = parser.parse_args()

    ponto_p = args.ponto_p
    if ponto_p is None:
        entrada = input(
            "Digite a posição do ponto P na mesma unidade da posição do CSV "
            "(ex.: 1.10 em metros ou 100 em centímetros): "
        ).strip().replace(",", ".")
        ponto_p = float(entrada)

    resultados = []
    for arquivo in args.arquivos:
        try:
            resultado = analisar_arquivo(
                caminho=arquivo,
                ponto_p_original=ponto_p,
                unidade=args.unidade_pos,
                max_intervalos=args.max_intervalos,
            )
            resultados.append(resultado)
            imprimir_resultado(resultado)
        except Exception as erro:
            print("\n" + "=" * 72)
            print(f"Erro ao analisar o arquivo {arquivo}:")
            print(f"{erro}")

    if resultados:
        salvar_resultados_csv(resultados, args.saida)
        print("\n" + "=" * 72)
        print(f"Tabela de resultados salva em: {args.saida}")


if __name__ == "__main__":
    main()
