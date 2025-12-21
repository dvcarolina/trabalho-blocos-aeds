#!/usr/bin/env python3
import struct
import os

# Configurações principais
BLOCK_SIZE = 512
DATA_FILE = "alunos.dat"
REORG_FILE = "alunos_reorg.dat"
MAP_FILE = "mapa_blocos.txt"

# Representa um bloco físico do arquivo
class Block:
    def __init__(self, size):
        self.size = size
        self.buf = bytearray(size)
        self.used = 0

    def remaining(self):
        return self.size - self.used

    def write(self, data):
        n = min(len(data), self.remaining())
        self.buf[self.used:self.used+n] = data[:n]
        self.used += n
        return n

# Controle geral do arquivo e dos metadados
class Storage:
    def __init__(self, filename, block_size):
        self.filename = filename
        self.block_size = block_size
        self.blocks = []
        self.index = {}          # matrícula -> (bloco, offset, tamanho)
        self.free_spaces = []    # espaços livres reaproveitáveis
        self.excluded_count = 0
        if os.path.exists(filename):
            self.load()

    # Carrega o arquivo em blocos
    def load(self):
        self.blocks = []
        with open(self.filename, "rb") as f:
            while True:
                data = f.read(self.block_size)
                if not data:
                    break
                b = Block(self.block_size)
                b.buf[:] = data
                b.used = self.block_size
                self.blocks.append(b)
        self.scan()

    # Reconstrói índice e lista de espaços livres
    def scan(self):
        self.index = {}
        self.free_spaces = []
        self.excluded_count = 0
        for bi, b in enumerate(self.blocks):
            off = 0
            while off + 5 <= self.block_size:
                flag = b.buf[off:off+1]
                if flag == b'\x00':
                    break
                size = struct.unpack(">I", b.buf[off+1:off+5])[0]
                total = size + 5
                if flag == b'*':  # registro excluído
                    self.free_spaces.append((bi, off, total))
                    self.excluded_count += 1
                else:             # registro ativo
                    rec = b.buf[off+5:off+5+size].decode("utf-8")
                    matricula = rec.split("|")[0]
                    self.index[matricula] = (bi, off, total)
                off += total

    # Grava os blocos novamente no arquivo
    def flush(self):
        with open(self.filename, "wb") as f:
            for b in self.blocks:
                f.write(bytes(b.buf))

    # Inserção reaproveitando espaço livre
    def insert(self, record):
        payload = record.encode("utf-8")
        entry = b'+' + struct.pack(">I", len(payload)) + payload

        for i, (bi, off, free) in enumerate(self.free_spaces):
            if free >= len(entry):
                b = self.blocks[bi]
                b.buf[off:off+len(entry)] = entry
                self.index[record.split("|")[0]] = (bi, off, len(entry))
                if free > len(entry):
                    self.free_spaces[i] = (bi, off+len(entry), free-len(entry))
                else:
                    self.free_spaces.pop(i)
                self.flush()
                return

        if not self.blocks or self.blocks[-1].remaining() < len(entry):
            self.blocks.append(Block(self.block_size))

        b = self.blocks[-1]
        off = b.used
        b.write(entry)
        self.index[record.split("|")[0]] = (len(self.blocks)-1, off, len(entry))
        self.flush()

    # Exclusão lógica
    def delete(self, matricula):
        if matricula not in self.index:
            return
        bi, off, size = self.index[matricula]
        b = self.blocks[bi]
        b.buf[off:off+1] = b'*'
        self.free_spaces.append((bi, off, size))
        del self.index[matricula]
        self.excluded_count += 1
        self.flush()

    # Atualização com realocação se necessário
    def update(self, matricula, new_record):
        if matricula not in self.index:
            return
        bi, off, size = self.index[matricula]
        payload = new_record.encode("utf-8")
        new_size = len(payload) + 5

        if new_size <= size:
            b = self.blocks[bi]
            b.buf[off:off+1] = b'+'
            b.buf[off+1:off+5] = struct.pack(">I", len(payload))
            b.buf[off+5:off+5+len(payload)] = payload
            del self.index[matricula]
            self.index[new_record.split("|")[0]] = (bi, off, new_size)
            if new_size < size:
                self.free_spaces.append((bi, off+new_size, size-new_size))
            self.flush()
        else:
            self.delete(matricula)
            self.insert(new_record)

    # Estatísticas gerais do arquivo
    def stats(self):
        total_blocks = len(self.blocks)
        capacity = total_blocks * self.block_size
        used = sum(b.used for b in self.blocks)
        return {
            "blocos": total_blocks,
            "ocupado": used,
            "capacidade": capacity,
            "eficiencia": (used / capacity * 100) if capacity else 0,
            "ativos": len(self.index),
            "excluidos": self.excluded_count
        }

    # Geração do mapa de ocupação
    def save_map(self):
        with open(MAP_FILE, "w", encoding="utf-8") as f:
            for i, b in enumerate(self.blocks, start=1):
                used = sum(1 for x in b.buf if x != 0)
                free = self.block_size - used
                pct = used / self.block_size * 100
                f.write(f"Bloco {i}: {used} bytes usados, {free} livres ({pct:.2f}%)\n")

    # Reorganização física do arquivo
    def reorganize(self):
        new = Storage(REORG_FILE, self.block_size)
        new.blocks = []
        new.index = {}
        for m in self.index:
            bi, off, size = self.index[m]
            b = self.blocks[bi]
            rec = b.buf[off+5:off+size].decode("utf-8")
            new.insert(rec)
        return new

# Impressão do relatório comparativo
def print_report(before, after):
    ganho = after["eficiencia"] - before["eficiencia"]
    print("\n===== RELATÓRIO DE REORGANIZAÇÃO =====")
    print("Antes:")
    print(f"Blocos: {before['blocos']}")
    print(f"Ocupação média: {before['eficiencia']:.2f}%")
    print(f"Registros ativos: {before['ativos']}")
    print(f"Registros excluídos: {before['excluidos']}")
    print("\nDepois:")
    print(f"Blocos: {after['blocos']}")
    print(f"Ocupação média: {after['eficiencia']:.2f}%")
    print(f"Registros ativos: {after['ativos']}")
    print(f"\nGanho de eficiência: {ganho:+.2f}%")
    print("====================================")

# Menu simples de uso
def menu():
    s = Storage(DATA_FILE, BLOCK_SIZE)
    while True:
        print("\n1 Inserir\n2 Editar\n3 Excluir\n4 Reorganizar\n5 Estatísticas\n6 Mapa de Blocos\n0 Sair")
        op = input("Opção: ").strip()
        if op == "1":
            s.insert(input("Registro: "))
        elif op == "2":
            s.update(input("Matrícula: "), input("Novo registro: "))
        elif op == "3":
            s.delete(input("Matrícula: "))
        elif op == "4":
            before = s.stats()
            after = s.reorganize().stats()
            print_report(before, after)
        elif op == "5":
            print(s.stats())
        elif op == "6":
            s.save_map()
            print("Mapa gerado.")
        elif op == "0":
            break

if __name__ == "__main__":
    menu()
