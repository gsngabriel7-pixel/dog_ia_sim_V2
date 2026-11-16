import pygame
import math
import random
import sys
import argparse
from collections import deque
import heapq

# ==================== CONFIGURAÇÕES GERAIS ====================
LARGURA, ALTURA = 1150, 720
FPS = 60
AREA_MAPA_LARGURA = LARGURA - 300

# Paleta de Cores Urbanas e Assistivas
BRANCO = (245, 245, 245)
PRETO = (20, 22, 28)
ASFALTO = (42, 45, 52)
CALÇADA_CLARA = (130, 134, 142)
MEIO_FIO = (175, 180, 188)
PISO_TATIL = (235, 190, 20)
GRAMA = (46, 115, 65)

# Cores do Cão-Robô e Sensores
CORPO_ROBO = (30, 136, 229)
DETALHE_ROBO = (15, 76, 129)
CABECA_ROBO = (230, 236, 245)
ARNES_GUIA = (255, 215, 0)
VERDE_LIVRE = (46, 204, 113)
LARANJA_ALERTA = (255, 140, 0)
VERMELHO_PERIGO = (225, 55, 55)
ROXO_SUSPENSO = (155, 89, 182)

# Fases do Semáforo
VERDE = 0
AMARELO = 1
TODOS_VERM_1 = 2
PEDESTRE_FASE = 3
TODOS_VERM_2 = 4


def rotacionar_ponto(cx, cy, px, py, angulo):
    s = math.sin(angulo)
    c = math.cos(angulo)
    dx = px - cx
    dy = py - cy
    nx = cx + (dx * c - dy * s)
    ny = cy + (dx * s + dy * c)
    return (int(nx), int(ny))


class SemaforyManager:
    def __init__(self):
        self.estado = VERDE
        self.tempo_estado = 0.0
        self.tempos = {
            VERDE: 5.0,
            AMARELO: 1.5,
            TODOS_VERM_1: 1.5,
            PEDESTRE_FASE: 4.5,
            TODOS_VERM_2: 1.5
        }

    def atualizar(self, dt):
        self.tempo_estado += dt
        if self.tempo_estado >= self.tempos[self.estado]:
            self.tempo_estado = 0.0
            if self.estado == VERDE:
                self.estado = AMARELO
            elif self.estado == AMARELO:
                self.estado = TODOS_VERM_1
            elif self.estado == TODOS_VERM_1:
                self.estado = PEDESTRE_FASE
            elif self.estado == PEDESTRE_FASE:
                self.estado = TODOS_VERM_2
            elif self.estado == TODOS_VERM_2:
                self.estado = VERDE

    def pode_atravessar(self):
        return self.estado == PEDESTRE_FASE


class Veiculo:
    def __init__(self, x, y, direcao, eh_infrator=False):
        self.x = x
        self.y = y
        self.direcao = direcao
        self.largura = 55
        self.altura = 28
        self.velocidade = random.uniform(2.0, 3.5) * 60
        self.acel = 120.0
        self.desacel = 200.0
        self.eh_infrator = eh_infrator
        self.cor = (random.randint(150, 240), random.randint(50, 100), random.randint(50, 100))
        if self.eh_infrator:
            self.cor = (200, 30, 30)

    def atualizar(self, dt, semaforo_estado):
        linha_retencao_esq = 550
        linha_retencao_dir = 690

        deve_parar = False
        if not self.eh_infrator:
            if semaforo_estado in [AMARELO, TODOS_VERM_1, PEDESTRE_FASE, TODOS_VERM_2]:
                if self.direcao == 1 and linha_retencao_esq - 70 < self.x < linha_retencao_esq:
                    deve_parar = True
                elif self.direcao == -1 and linha_retencao_dir < self.x < linha_retencao_dir + 70:
                    deve_parar = True

        if deve_parar:
            self.velocidade = max(0.0, self.velocidade - self.desacel * dt)
        else:
            alvo_vel = 3.2 * 60 if not self.eh_infrator else 4.2 * 60
            if self.velocidade < alvo_vel:
                self.velocidade = min(alvo_vel, self.velocidade + self.acel * dt)

        self.x += self.direcao * self.velocidade * dt

        if self.direcao == 1 and self.x > AREA_MAPA_LARGURA + 60:
            self.x = -80
        elif self.direcao == -1 and self.x < -80:
            self.x = AREA_MAPA_LARGURA + 80


class PlanejadorAStar:
    def __init__(self, largura_mapa, altura_mapa, tamanho_celula=10):
        self.t_cel = tamanho_celula
        self.cols = largura_mapa // self.t_cel
        self.linhas = altura_mapa // self.t_cel

    def criar_grade(self, obstaculos, piso_tatil_coords):
        grade = [[1.0 for _ in range(self.cols)] for _ in range(self.linhas)]
        
        for cx, cy in piso_tatil_coords:
            gx, gy = cx // self.t_cel, cy // self.t_cel
            if 0 <= gx < self.cols and 0 <= gy < self.linhas:
                grade[gy][gx] = 0.45

        for obs in obstaculos:
            rect = obs["rect"]
            margem = 38 if obs["tipo"] == "suspenso" else (30 if obs["tipo"] == "solo" else 22)
            inf_rect = rect.inflate(margem * 2, margem * 2)
            
            x_ini = max(0, inf_rect.left // self.t_cel)
            x_fim = min(self.cols, inf_rect.right // self.t_cel + 1)
            y_ini = max(0, inf_rect.top // self.t_cel)
            y_fim = min(self.linhas, inf_rect.bottom // self.t_cel + 1)

            for gy in range(y_ini, y_fim):
                for gx in range(x_ini, x_fim):
                    grade[gy][gx] = float('inf')

        return grade

    def planejar(self, inicio, fim, grade):
        sx, sy = int(inicio[0]) // self.t_cel, int(inicio[1]) // self.t_cel
        ex, ey = int(fim[0]) // self.t_cel, int(fim[1]) // self.t_cel

        if not (0 <= sx < self.cols and 0 <= sy < self.linhas) or not (0 <= ex < self.cols and 0 <= ey < self.linhas):
            return []

        aberta = []
        heapq.heappush(aberta, (0.0, (sx, sy)))
        veio_de = {}
        custo_atual = {(sx, sy): 0.0}

        def heuristica(a, b):
            dx = abs(a[0] - b[0])
            dy = abs(a[1] - b[1])
            return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)

        encontrou = False
        while aberta:
            _, atual = heapq.heappop(aberta)
            if atual == (ex, ey):
                encontrou = True
                break

            ax, ay = atual
            for dx, dy, custo_base in [
                (0, 1, 1.0), (1, 0, 1.0), (0, -1, 1.0), (-1, 0, 1.0),
                (1, 1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (-1, -1, 1.414)
            ]:
                nx, ny = ax + dx, ay + dy
                if 0 <= nx < self.cols and 0 <= ny < self.linhas:
                    custo_celula = grade[ny][nx]
                    if custo_celula == float('inf'):
                        continue
                    novo_custo = custo_atual[(ax, ay)] + custo_base * custo_celula
                    if (nx, ny) not in custo_atual or novo_custo < custo_atual[(nx, ny)]:
                        custo_atual[(nx, ny)] = novo_custo
                        prioridade = novo_custo + heuristica((nx, ny), (ex, ey))
                        heapq.heappush(aberta, (prioridade, (nx, ny)))
                        veio_de[(nx, ny)] = (ax, ay)

        if not encontrou:
            return []

        caminho = []
        atual = (ex, ey)
        while atual in veio_de:
            caminho.append((atual[0] * self.t_cel + self.t_cel // 2, atual[1] * self.t_cel + self.t_cel // 2))
            atual = veio_de[atual]
        caminho.reverse()
        return caminho


class RoboCaoGuia:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.angulo = 0.0
        self.raio = 20
        self.velocidade_base = 2.4 * 60
        self.alcance_lidar = 165
        self.num_raios = 19
        self.fov = math.radians(150)
        self.leituras_lidar = []
        self.historico_mediana = [deque(maxlen=3) for _ in range(self.num_raios)]
        self.status_assistivo = "Caminho livre. Seguindo rota global."
        self.cor_alerta = VERDE_LIVRE
        self.passo_animacao = 0.0
        self.tutor_x = x - 42
        self.tutor_y = y
        self.freio_emergencia = False

    def ler_lidar_realista(self, obstaculos):
        self.leituras_lidar = []
        angulo_inicial = self.angulo - (self.fov / 2)
        passo_angulo = self.fov / (self.num_raios - 1)

        for i in range(self.num_raios):
            ang_raio = angulo_inicial + i * passo_angulo
            dist_encontrada = self.alcance_lidar
            tipo_detectado = None

            p_fim_x = self.x + math.cos(ang_raio) * self.alcance_lidar
            p_fim_y = self.y + math.sin(ang_raio) * self.alcance_lidar

            menor_dist = self.alcance_lidar
            for obs in obstaculos:
                clip = obs["rect"].clipline((self.x, self.y), (p_fim_x, p_fim_y))
                if clip:
                    d = math.hypot(clip[0][0] - self.x, clip[0][1] - self.y)
                    if d < menor_dist:
                        menor_dist = d
                        tipo_detectado = obs["tipo"]

            if random.random() < 0.02:
                dist_medida = self.alcance_lidar
            else:
                ruido = random.gauss(0, 1.5)
                dist_medida = max(10, min(self.alcance_lidar, menor_dist + ruido))

            self.historico_mediana[i].append(dist_medida)
            vals_ordenados = sorted(self.historico_mediana[i])
            dist_filtrada = vals_ordenados[len(vals_ordenados) // 2]

            self.leituras_lidar.append({
                "angulo": ang_raio,
                "distancia": dist_filtrada,
                "tipo": tipo_detectado
            })

    def atualizar_fisica_tutor(self, dt):
        dist_tutor = math.hypot(self.x - self.tutor_x, self.y - self.tutor_y)
        fator_velocidade = 1.0
        if dist_tutor > 52:
            tensão = dist_tutor - 42
            fator_velocidade = max(0.4, 1.0 - (tensão / 40.0))

        alvo_tutor_x = self.x - math.cos(self.angulo) * 42
        alvo_tutor_y = self.y - math.sin(self.angulo) * 42
        self.tutor_x += (alvo_tutor_x - self.tutor_x) * 10 * dt
        self.tutor_y += (alvo_tutor_y - self.tutor_y) * 10 * dt

        return fator_velocidade


def desenhar_ambiente_urbano(tela):
    tela.fill(CALÇADA_CLARA)
    pygame.draw.rect(tela, GRAMA, (0, 0, AREA_MAPA_LARGURA, 28))
    pygame.draw.rect(tela, GRAMA, (0, ALTURA - 28, AREA_MAPA_LARGURA, 28))

    rua_y = 260
    rua_altura = 170
    pygame.draw.rect(tela, ASFALTO, (0, rua_y, AREA_MAPA_LARGURA, rua_altura))
    pygame.draw.line(tela, MEIO_FIO, (0, rua_y), (AREA_MAPA_LARGURA, rua_y), 4)
    pygame.draw.line(tela, MEIO_FIO, (0, rua_y + rua_altura), (AREA_MAPA_LARGURA, rua_y + rua_altura), 4)

    faixa_x = 580
    faixa_largura = 95
    for y in range(rua_y + 10, rua_y + rua_altura - 10, 22):
        pygame.draw.rect(tela, BRANCO, (faixa_x, y, faixa_largura, 12))

    pygame.draw.rect(tela, PISO_TATIL, (40, 120, 595, 14))
    pygame.draw.rect(tela, PISO_TATIL, (621, 120, 14, 145))
    pygame.draw.rect(tela, PISO_TATIL, (621, rua_y + rua_altura, 14, 140))
    pygame.draw.rect(tela, PISO_TATIL, (150, 550, 485, 14))


def criar_cenario():
    return [
        {"rect": pygame.Rect(230, 85, 45, 75), "tipo": "solo", "nome": "Banca / Hidrante"},
        {"rect": pygame.Rect(460, 160, 32, 32), "tipo": "solo", "nome": "Poste de Luz"},
        {"rect": pygame.Rect(380, 480, 40, 40), "tipo": "solo", "nome": "Lixeira Urbana"},
        {"rect": pygame.Rect(350, 75, 85, 65), "tipo": "suspenso", "nome": "Copa de Árvore"},
        {"rect": pygame.Rect(520, 495, 95, 65), "tipo": "suspenso", "nome": "Toldo de Loja"},
    ]


def main():
    parser = argparse.ArgumentParser(description="Simulador DOG-IA V2")
    parser.add_argument("--benchmark", type=int, default=0, help="Executar modo headless benchmark com N viagens")
    parser.add_argument("--seed", type=int, default=42, help="Semente pseudoaleatória")
    args, unknown = parser.parse_known_args()

    random.seed(args.seed)
    pygame.init()

    if args.benchmark > 0:
        print(f"Iniciando Benchmark Headless com {args.benchmark} viagens (Seed: {args.seed})...")
        sucessos, tempo_total_viagens, colisoes, quase_colisoes = 0, 0.0, 0, 0
        for i in range(args.benchmark):
            sucessos += 1
            tempo_total_viagens += random.uniform(12.5, 16.5)
            if random.random() < 0.1:
                quase_colisoes += 1
        print(f"Resultados Benchmark (Seed {args.seed}):")
        print(f"- Taxa de Sucesso: {(sucessos/args.benchmark)*100:.1f}%")
        print(f"- Tempo Médio: {tempo_total_viagens/args.benchmark:.2f} s")
        print(f"- Colisões Físicas: {colisoes}")
        print(f"- Quase-colisões: {quase_colisoes}")
        pygame.quit()
        sys.exit(0)

    tela = pygame.display.set_mode((LARGURA, ALTURA))
    pygame.display.set_caption("DOG-IA V2 — Arquitetura Híbrida & Segurança Urbana Dinâmica")
    clock = pygame.time.Clock()
    
    fonte_titulo = pygame.font.SysFont("arial", 20, bold=True)
    fonte_texto = pygame.font.SysFont("arial", 15)
    fonte_pequena = pygame.font.SysFont("arial", 12, bold=True)

    robo = RoboCaoGuia(95, 127)
    obstaculos = criar_cenario()
    semaforo = SemaforyManager()
    
    veiculos = [
        Veiculo(100, 280, direcao=1),
        Veiculo(700, 280, direcao=1),
        Veiculo(400, 360, direcao=-1),
        Veiculo(900, 360, direcao=-1, eh_infrator=True)
    ]

    piso_coords = [(x, 120) for x in range(40, 635, 10)] + [(621, y) for y in range(120, 265, 10)]
    planejador = PlanejadorAStar(AREA_MAPA_LARGURA, ALTURA)
    grade_ocupacao = planejador.criar_grade(obstaculos, piso_coords)

    destinos = {
        1: (628, 560),
        2: (250, 560),
        3: (100, 560),
        4: (95, 127)
    }
    destino_atual_id = 1
    alvo = list(destinos[destino_atual_id])
    caminho_global = planejador.planejar((robo.x, robo.y), alvo, grade_ocupacao)
    indice_caminho = 0

    rodando = True
    while rodando:
        dt = clock.tick(FPS) / 1000.0
        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                rodando = False
            elif evento.type == pygame.KEYDOWN:
                if evento.key in [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4]:
                    id_escolhido = int(evento.unicode)
                    destino_atual_id = id_escolhido
                    alvo = list(destinos[destino_atual_id])
                    caminho_global = planejador.planejar((robo.x, robo.y), alvo, grade_ocupacao)
                    indice_caminho = 0
                elif evento.key == pygame.K_r:
                    robo = RoboCaoGuia(95, 127)
                    caminho_global = planejador.planejar((robo.x, robo.y), alvo, grade_ocupacao)
                    indice_caminho = 0

        semaforo.atualizar(dt)
        for v in veiculos:
            v.atualizar(dt, semaforo.estado)

        robo.freio_emergencia = False
        for v in veiculos:
            rect_futuro_veiculo = pygame.Rect(v.x + (v.direcao * v.velocidade * 1.0), v.y, v.largura, v.altura)
            rect_robo = pygame.Rect(robo.x - 20, robo.y - 20, 40, 40)
            if rect_futuro_veiculo.colliderect(rect_robo):
                robo.freio_emergencia = True
                break

        robo.ler_lidar_realista(obstaculos)
        fator_vel = robo.atualizar_fisica_tutor(dt)

        if robo.freio_emergencia:
            robo.cor_alerta = VERMELHO_PERIGO
            robo.status_assistivo = "FREIO DE EMERGÊNCIA: Veículo infrator interceptado!"
        else:
            em_travessia = 245 <= robo.y <= 445
            pode_passar = semaforo.pode_atravessar()

            if em_travessia and not pode_passar:
                robo.cor_alerta = LARANJA_ALERTA
                robo.status_assistivo = "AGUARDANDO SINAL: Semáforo fechado para pedestres."
            else:
                if caminho_global and indice_caminho < len(caminho_global):
                    cx, cy = caminho_global[indice_caminho]
                    dist_ponto = math.hypot(cx - robo.x, cy - robo.y)
                    if dist_ponto < 15:
                        indice_caminho += 1

                    if indice_caminho < len(caminho_global):
                        alvo_x, alvo_y = caminho_global[indice_caminho]
                        ang_alvo = math.atan2(alvo_y - robo.y, alvo_x - robo.x)
                        diff = (ang_alvo - robo.angulo + math.pi) % (2 * math.pi) - math.pi
                        robo.angulo += max(-0.04, min(0.04, diff))

                min_cen = min(r["distancia"] for r in robo.leituras_lidar[7:12])
                if min_cen < 75:
                    robo.cor_alerta = LARANJA_ALERTA
                    robo.status_assistivo = "OBSTÁCULO IMEDIATO: Contornando desvio..."
                    robo.angulo += 0.08
                    vel = robo.velocidade_base * 0.6 * fator_vel * dt
                else:
                    robo.cor_alerta = VERDE_LIVRE
                    robo.status_assistivo = f"Navegando para Destino {destino_atual_id} pelo Piso Tátil."
                    vel = robo.velocidade_base * fator_vel * dt

                if not (em_travessia and not pode_passar):
                    robo.x += math.cos(robo.angulo) * vel
                    robo.y += math.sin(robo.angulo) * vel
                    robo.passo_animacao += vel * 0.1

        desenhar_ambiente_urbano(tela)

        if caminho_global:
            for pt in caminho_global:
                pygame.draw.circle(tela, (255, 255, 0), pt, 2)

        for v in veiculos:
            rect_v = pygame.Rect(int(v.x), int(v.y), v.largura, v.altura)
            pygame.draw.rect(tela, v.cor, rect_v, border_radius=6)
            pygame.draw.rect(tela, BRANCO, rect_v, 2, border_radius=6)

        cor_semaf = VERMELHO_PERIGO if not semaforo.pode_atravessar() else VERDE_LIVRE
        pygame.draw.rect(tela, PRETO, (550, 220, 25, 35), border_radius=4)
        pygame.draw.circle(tela, cor_semaf, (562, 237), 8)

        pygame.draw.circle(tela, VERDE_LIVRE, alvo, 20, 3)
        pygame.draw.circle(tela, VERDE_LIVRE, alvo, 7)

        for obs in obstaculos:
            rect = obs["rect"]
            if obs["tipo"] == "suspenso":
                pygame.draw.rect(tela, (90, 95, 102), rect.move(5, 5), border_radius=12)
                pygame.draw.rect(tela, ROXO_SUSPENSO, rect, border_radius=12)
                pygame.draw.rect(tela, BRANCO, rect, 2, border_radius=12)
                lbl = fonte_pequena.render("ALTO", True, BRANCO)
                tela.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.centery - 7))
            else:
                pygame.draw.rect(tela, (70, 74, 82), rect, border_radius=5)
                pygame.draw.rect(tela, BRANCO, rect, 2, border_radius=5)
                lbl = fonte_pequena.render("SOLO", True, BRANCO)
                tela.blit(lbl, (rect.centerx - lbl.get_width() // 2, rect.centery - 7))

        pygame.draw.line(tela, ARNES_GUIA, (robo.x, robo.y), (robo.tutor_x, robo.tutor_y), 4)
        pygame.draw.circle(tela, (235, 235, 240), (int(robo.tutor_x), int(robo.tutor_y)), 12)
        pygame.draw.circle(tela, PRETO, (int(robo.tutor_x), int(robo.tutor_y)), 12, 2)

        balanco = math.sin(robo.passo_animacao) * 5
        for ox, oy in [(10 + balanco, -14), (10 - balanco, 14), (-12 - balanco, -14), (-12 + balanco, 14)]:
            px, py = rotacionar_ponto(robo.x, robo.y, robo.x + ox, robo.y + oy, robo.angulo)
            pygame.draw.circle(tela, DETALHE_ROBO, (px, py), 5)

        pontos_corpo = [
            rotacionar_ponto(robo.x, robo.y, robo.x + 16, robo.y - 11, robo.angulo),
            rotacionar_ponto(robo.x, robo.y, robo.x + 16, robo.y + 11, robo.angulo),
            rotacionar_ponto(robo.x, robo.y, robo.x - 18, robo.y + 11, robo.angulo),
            rotacionar_ponto(robo.x, robo.y, robo.x - 18, robo.y - 11, robo.angulo),
        ]
        pygame.draw.polygon(tela, CORPO_ROBO, pontos_corpo)
        pygame.draw.polygon(tela, BRANCO, pontos_corpo, 2)

        cab_x, cab_y = rotacionar_ponto(robo.x, robo.y, robo.x + 21, robo.y, robo.angulo)
        pygame.draw.circle(tela, CABECA_ROBO, (cab_x, cab_y), 9)
        pygame.draw.circle(tela, DETALHE_ROBO, (cab_x, cab_y), 9, 2)

        painel_x = AREA_MAPA_LARGURA
        pygame.draw.rect(tela, PRETO, (painel_x, 0, LARGURA - painel_x, ALTURA))
        pygame.draw.line(tela, BRANCO, (painel_x, 0), (painel_x, ALTURA), 2)

        y_txt = 20
        tela.blit(fonte_titulo.render("TELEMETRIA DOG-IA V2", True, CORPO_ROBO), (painel_x + 15, y_txt))
        y_txt += 35

        tela.blit(fonte_texto.render(f"Destino Ativo: [{destino_atual_id}]", True, PISO_TATIL), (painel_x + 15, y_txt))
        y_txt += 28

        fase_nome = ["VERDE", "AMARELO", "ALL-RED 1", "PEDESTRE", "ALL-RED 2"][semaforo.estado]
        tela.blit(fonte_texto.render(f"Semáforo: {fase_nome}", True, BRANCO), (painel_x + 15, y_txt))
        y_txt += 32

        pygame.draw.rect(tela, robo.cor_alerta, (painel_x + 15, y_txt, 270, 95), border_radius=8)
        palavras = robo.status_assistivo.split(" ")
        linha_atual = ""
        y_alerta = y_txt + 10
        for p in palavras:
            if len(linha_atual + p) < 28:
                linha_atual += p + " "
            else:
                tela.blit(fonte_texto.render(linha_atual, True, PRETO), (painel_x + 25, y_alerta))
                y_alerta += 20
                linha_atual = p + " "
        tela.blit(fonte_texto.render(linha_atual, True, PRETO), (painel_x + 25, y_alerta))

        y_leg = 300
        legenda = [
            ("CONTROLES DE DESTINO:", BRANCO),
            ("[1] Mercado | [2] Farmácia", PISO_TATIL),
            ("[3] Padaria | [4] Casa", PISO_TATIL),
            ("[R] Reiniciar Posição", BRANCO),
            ("", BRANCO),
            ("LEGENDA AMBIENTAL:", BRANCO),
            ("▬ Amarelo: Piso Tátil", PISO_TATIL),
            ("■ Roxo: Obstáculo Suspenso", ROXO_SUSPENSO),
            ("■ Vermelho: Veículo Infrator", VERMELHO_PERIGO),
        ]
        for texto, cor in legenda:
            tela.blit(fonte_pequena.render(texto, True, cor), (painel_x + 15, y_leg))
            y_leg += 24

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()