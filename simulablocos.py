#!/usr/bin/env python3
"""
Simulação de armazenamento em blocos para o Trabalho Prático (AEDS II).
Gera registros fictícios e organiza em blocos conforme:
- registros de tamanho fixo;
- registros de tamanho variável (contíguos ou espalhados).

Gera 'alunos.dat' com os blocos gravados sequencialmente.

"""

import struct
import random
import os
import sys

# ----------- CONFIGURÁVEIS / LIMITES  -----------
MAX_NOME = 50
MAX_CPF = 11
MAX_CURSO = 30
MAX_FILIA = 30
# inteiros: matrícula 9 dígitos, ano 4 dígitos; CA: float com 2 casas
MATRICULA_DIGITS = 9
ANO_DIGITS = 4

# ----------- GERAÇÃO DE DADOS FICTÍCIOS (simples, sem libs externas) -----------
FIRST_NAMES = ["Ana", "Bruno", "Carlos", "Daniela", "Eduardo", "Fabiana", "Gabriel", "Helena", "Igor", "Juliana"]
LAST_NAMES = ["Silva", "Souza", "Oliveira", "Pereira", "Almeida", "Costa", "Santos", "Rocha"]
COURSES = ["Engenharia", "Direito", "Medicina", "Ciência da Computação", "Arquitetura", "Economia", "Biologia"]

def random_name(max_len):
    # cria um nome razoável dentro do limite
    name = random.choice(FIRST_NAMES) + " " + random.choice(LAST_NAMES)
    extra = ""
    while len(name + extra) < min(max_len, len(name) + 10) and random.random() < 0.3:
        extra = extra + " " + random.choice(LAST_NAMES)
    name = (name + extra)[:max_len]
    return name

def random_cpf():
    # gera string numérica de 11 dígitos
    return "".join(str(random.randint(0,9)) for _ in range(MAX_CPF))

def random_matricula():
    return str(random.randint(10**(MATRICULA_DIGITS-1), 10**MATRICULA_DIGITS - 1))

def random_ano():
    return str(random.randint(1990, 2025))

def random_ca():
    return "{:.2f}".format(random.uniform(0.00, 10.00))

def generate_records(n):
    records = []
    for _ in range(n):
        rec = {
            "matricula": random_matricula(),
            "nome": random_name(MAX_NOME),
            "cpf": random_cpf(),
            "curso": random.choice(COURSES)[:MAX_CURSO],
            "mae": random_name(MAX_FILIA),
            "pai": random_name(MAX_FILIA),
            "ano": random_ano(),
            "ca": random_ca()
        }
        records.append(rec)
    return records

# ----------- SERIALIZAÇÃO -----------
def serialize_fixed(rec, pad_byte=b'#'):
    """
    Monta registro de tamanho fixo: concatena campos com padding para os tamanhos máximos.
    Retorna bytes com tamanho constante (mesmo para todos).
    Ordem dos campos: matricula(9), nome(50), cpf(11), curso(30), mae(30), pai(30), ano(4), ca(8)
    
    Nota: CA reservarei 8 bytes (por exemplo "9.99   ").

    """
    fields = []
    # matrícula: 9 caracteres, zero-padded à esquerda
    mat = rec["matricula"].zfill(MATRICULA_DIGITS)
    fields.append(mat.encode('ascii'))
    # nome: MAX_NOME
    nome = rec["nome"][:MAX_NOME]
    fields.append(nome.encode('utf-8').ljust(MAX_NOME, pad_byte))
    # cpf
    cpf = rec["cpf"].zfill(MAX_CPF)
    fields.append(cpf.encode('ascii'))
    # curso
    curso = rec["curso"][:MAX_CURSO]
    fields.append(curso.encode('utf-8').ljust(MAX_CURSO, pad_byte))
    # mae
    mae = rec["mae"][:MAX_FILIA]
    fields.append(mae.encode('utf-8').ljust(MAX_FILIA, pad_byte))
    # pai
    pai = rec["pai"][:MAX_FILIA]
    fields.append(pai.encode('utf-8').ljust(MAX_FILIA, pad_byte))
    # ano
    ano = rec["ano"].zfill(ANO_DIGITS)
    fields.append(ano.encode('ascii'))
    # ca: 8 bytes reserved (e.g. "9.85    ")
    ca = rec["ca"]
    fields.append(ca.encode('ascii').ljust(8, pad_byte))
    return b"".join(fields)

# Para registros de tamanho variável, usamos dados precedidos de tamanho: 4 bytes (inteiro sem sinal, big-endian) = tamanho do conteúdo
def serialize_variable(rec):
    """
    Serializa campos em formato compacto (campo separados por '|') e retorna payload bytes.
    Payload bytes não inclui o prefixo de 4 bytes — isso será adicionado na escrita de bloco.

    """
    # Escolha de formatação: campo1|campo2|... em ascii/utf-8
    parts = [
        rec["matricula"],
        rec["nome"],
        rec["cpf"],
        rec["curso"],
        rec["mae"],
        rec["pai"],
        rec["ano"],
        rec["ca"]
    ]
    s = "|".join(parts)
    data = s.encode('utf-8')
    return data

# ----------- SIMULAÇÃO DE BLOCOS E GRAVAÇÃO -----------
class Block:
    def __init__(self, size):
        self.size = size
        self.buf = bytearray(size)
        self.used = 0  # bytes ocupados

    def remaining(self):
        return self.size - self.used

    def write_bytes(self, data: bytes):
        """
        Escreve até o máximo possível. Retorna n_bytes_escritos.

        """
        n = min(len(data), self.remaining())
        if n <= 0:
            return 0
        self.buf[self.used:self.used+n] = data[:n]
        self.used += n
        return n

def simulate_fixed(records, block_size, pad_byte=b'#'):
    # calcula o tamanho fixo usando um registro exemplo
    sample = {
        "matricula": "0"*MATRICULA_DIGITS,
        "nome": "A"*MAX_NOME,
        "cpf": "0"*MAX_CPF,
        "curso": "C"*MAX_CURSO,
        "mae": "M"*MAX_FILIA,
        "pai": "P"*MAX_FILIA,
        "ano": "0"*ANO_DIGITS,
        "ca": "9.99"
    }

    rec_size = len(serialize_fixed(sample, pad_byte=pad_byte))

    # garante que um registro fixo cabe dentro de um bloco
    if rec_size > block_size:
        raise ValueError(f"Registro fixo ({rec_size} bytes) maior que tamanho do bloco ({block_size} bytes).")

    blocks = []
    current = Block(block_size)
    blocks.append(current)
    total_data_bytes = 0

    for rec in records:
        data = serialize_fixed(rec, pad_byte=pad_byte)

        # troca de bloco se não couber inteiro
        if current.remaining() < rec_size:
            current = Block(block_size)
            blocks.append(current)

        written = current.write_bytes(data)
        assert written == rec_size

        total_data_bytes += rec_size

    return blocks, total_data_bytes, rec_size


def simulate_variable(records, block_size, espalhado=False):
    """
    Simulação para registros de tamanho variável.
    Cada registro → payload em bytes (via serialize_variable).
    Armazenamos com um prefixo de 4 bytes indicando o tamanho do payload.
    Se espalhado==False (contíguo): se o bloco não comportar o registro inteiro (4+tamanho),
        o registro é movido integralmente para o próximo bloco.
    Se espalhado==True: grava-se o que couber no bloco atual e o restante continua
        em blocos seguintes. Para indicar continuidade, colocamos um pequeno cabeçalho
        antes de cada fragmento:
        - 1 byte de flag: 0x00 = último fragmento (ou único), 0x01 = ainda há continuidade
        - 4 bytes (big-endian) = total_record_id (ID único por registro) — ajuda na identificação (opcional)
        - 4 bytes = tamanho total do payload (usamos o tamanho total por clareza)
        Depois do cabeçalho, vêm os bytes do fragmento.
    Isto é uma simulação: cabeçalhos consomem espaço nos blocos.
    """
    blocks = []
    current = Block(block_size)
    blocks.append(current)
    total_data_bytes = 0
    record_id = 1
    for rec in records:
        payload = serialize_variable(rec)
        payload_len = len(payload)
        # registro completo armazenado no modo contíguo: 4 bytes do tamanho + payload
        full_record = struct.pack(">I", payload_len) + payload  # prefixo de 4 bytes com o tamanho
        total_data_bytes += len(full_record)
        if not espalhado:
            # contíguo: se não couber, mover para o próximo bloco
            if current.remaining() < len(full_record):
                current = Block(block_size)
                blocks.append(current)
            written = current.write_bytes(full_record)
            assert written == len(full_record)
        else:
            # espalhado: fragmentos com cabeçalho pequeno em cada fragmento
            # formato do cabeçalho: 1 byte flag, 4 bytes record_id, 4 bytes tamanho_total_payload
            # flag 0x01 = haverá mais fragmentos; 0x00 = último fragmento
            header_static = struct.pack(">I", record_id) + struct.pack(">I", payload_len)
            # mas precisamos colocar a flag antes, então o cabeçalho fica (flag + record_id + tamanho_total)
            bytes_remaining = len(payload)
            cursor = 0
            # incluiremos o cabeçalho e quantos bytes do payload couberem
            while bytes_remaining > 0:
                # determinar quantos bytes do payload cabem considerando o espaço gasto pelo cabeçalho
                # overhead: 1 (flag) + 4 (record_id) + 4 (tamanho_total)
                overhead = 1 + 4 + 4
                avail = current.remaining()
                if avail <= overhead:
                    # nem o cabeçalho cabe → abrir novo bloco
                    current = Block(block_size)
                    blocks.append(current)
                    avail = current.remaining()
                # quantos bytes do payload cabem neste fragmento
                frag_payload_space = avail - overhead
                frag_payload_space = max(frag_payload_space, 0)
                take = min(bytes_remaining, frag_payload_space)
                # decidir flag: se ainda sobrar payload depois desse fragmento → flag=1; senão flag=0
                flag = 1 if (bytes_remaining - take) > 0 else 0
                # montar fragmento
                frag_header = bytes([flag]) + struct.pack(">I", record_id) + struct.pack(">I", payload_len)
                frag_data = payload[cursor:cursor+take]
                frag = frag_header + frag_data
                written = current.write_bytes(frag)
                # se não conseguir escrever o fragmento todo (não deveria ocorrer), abrir novo bloco
                if written < len(frag):
                    # caso extremo de escrita parcial do cabeçalho: ignorado para manter simplicidade
                    pass
                cursor += take
                bytes_remaining -= take
                if bytes_remaining > 0:
                    # ainda há payload → próximo fragmento vai para um novo bloco
                    current = Block(block_size)
                    blocks.append(current)
            record_id += 1
    return blocks, total_data_bytes


# ----------- ESTATÍSTICAS E MAPA -----------
def compute_stats(blocks, total_data_bytes):
    total_blocks = len(blocks)
    block_usages = [b.used for b in blocks]
    total_capacity = total_blocks * blocks[0].size if total_blocks > 0 else 0
    avg_occupancy = (sum(block_usages) / total_capacity * 100) if total_capacity > 0 else 0.0
    partially_used = sum(1 for u in block_usages if 0 < u < blocks[0].size)
    efficiency = (total_data_bytes / total_capacity * 100) if total_capacity > 0 else 0.0
    return {
        "total_blocks": total_blocks,
        "block_usages": block_usages,
        "avg_occupancy_percent": avg_occupancy,
        "partially_used_blocks": partially_used,
        "efficiency_percent": efficiency,
        "total_data_bytes": total_data_bytes,
        "total_capacity_bytes": total_capacity
    }

def print_map_and_stats(stats, block_size):
    print("\n--- MAPA DE BLOCOS ---")
    for i, used in enumerate(stats["block_usages"], start=1):
        pct = used / block_size * 100
        print(f"Bloco {i}: {used} bytes ({pct:.1f}% cheio)")
    print(f"\nTotal de blocos: {stats['total_blocks']}")
    print(f"Percentual médio de ocupação: {stats['avg_occupancy_percent']:.2f}%")
    print(f"Número de blocos parcialmente utilizados: {stats['partially_used_blocks']}")
    print(f"Eficiência do armazenamento: {stats['efficiency_percent']:.2f}%")
    print(f"Total bytes de dados úteis: {stats['total_data_bytes']} / capacidade total {stats['total_capacity_bytes']}")

# ----------- GRAVAÇÃO DO ARQUIVO .DAT -----------
def write_dat(blocks, filename="alunos.dat"):
    with open(filename, "wb") as f:
        for b in blocks:
            # gravar todo o bloco (incluindo bytes não usados). Isso simula blocos inteiros no disco.
            f.write(bytes(b.buf))

# ----------- INTERFACE SIMPLES DE EXECUÇÃO -----------
def main():
    print("Simulador de armazenamento em blocos - AEDS II (Python)")
    try:
        n = int(input("Número de registros a gerar (ex: 100): ").strip())
    except:
        print("Entrada inválida. Usando 50 registros.")
        n = 50
    try:
        block_size = int(input("Tamanho do bloco em bytes (ex: 512): ").strip())
    except:
        print("Entrada inválida. Usando 512 bytes.")
        block_size = 512

    mode = None
    while mode not in ("1", "2"):
        print("Modo de armazenamento: 1) Tamanho fixo  2) Tamanho variável")
        mode = input("Escolha 1 ou 2: ").strip()

    records = generate_records(n)
    if mode == "1":
        pad = input("Caractere de preenchimento para campos (pad) [Enter -> '#']: ")
        pad_byte = b'#' if pad == "" else pad.encode('utf-8')[0:1]
        # simula fixo
        blocks, total_data_bytes, rec_size = simulate_fixed(records, block_size, pad_byte=pad_byte)
        print(f"\nRegistro fixo tamanho (bytes): {rec_size}")
    else:
        espalhado = None
        while espalhado not in ("1","2"):
            print("Registros variáveis: 1) Contíguos (sem espalhamento)  2) Espalhados (fragmentados)")
            espalhado = input("Escolha 1 ou 2: ").strip()
        blocks, total_data_bytes = simulate_variable(records, block_size, espalhado == "2")

    # grava arquivo .dat
    outname = "alunos.dat"
    write_dat(blocks, outname)
    print(f"\nArquivo '{outname}' gravado com {len(blocks)} blocos (cada bloco {block_size} bytes).")

    # estatísticas
    stats = compute_stats(blocks, total_data_bytes)
    print_map_and_stats(stats, block_size)

    # opcional: salvar mapa textual
    mapa_txt = "mapa_blocos.txt"
    with open(mapa_txt, "w", encoding="utf-8") as f:
        for i, used in enumerate(stats["block_usages"], start=1):
            pct = used / block_size * 100
            f.write(f"Bloco {i}: {used} bytes ({pct:.1f}% cheio)\n")
        f.write(f"\nTotal de blocos: {stats['total_blocks']}\n")
        f.write(f"Percentual médio de ocupação: {stats['avg_occupancy_percent']:.2f}%\n")
        f.write(f"Número de blocos parcialmente utilizados: {stats['partially_used_blocks']}\n")
        f.write(f"Eficiência do armazenamento: {stats['efficiency_percent']:.2f}%\n")
    print(f"Mapa textual salvo em '{mapa_txt}'.")

if __name__ == "__main__":
    main()
