---
type: benchmark-methodology
title: Benchmarks CPU de raios e propagação difusa
status: validated-on-ifro
---

# Benchmarks CPU de raios e propagação difusa

Código de laboratório, **sem contato com hardware, Tenda ou IoT**. Destina-se a comparar **kernels de interseção de raios** em CPUs antigas e modernas. Não é renderizador fotorealista completo e não mede latência Wi-Fi.

## Duas cargas de trabalho independentes

1. `embree_bench.cpp`: 80.000 raios primários contra 2, 256 e 1.024 caixas (12 triângulos por caixa). Compara `Embree rtcIntersect1` com uma implementação direta de Möller–Trumbore, sem BVH. Valida acertos de uma amostra de raios. Reporta tempo de construção da BVH e interseções por segundo. A comparação direta favorece métodos com aceleração espacial em cenas grandes, como esperado. Não é uma comparação com Mitsuba, PBRT ou RTXPT.
2. `embree_photon_bench.cpp`: 50.000 partículas virtuais originadas de uma fonte dentro de uma sala 3D, com até 1, 2, 4 ou 8 reflexões **difusas de Lambert** (amostragem por cosseno do hemisfério), atenuação de energia em 0,75 por contato e interseção via Embree. Usa duas ou 256 caixas. Reporta trajetória iniciada/s, consultas de interseção/s, contatos e soma de energia ponderada. **Não inclui** amostragem de iluminação direta, MIS, sensor/câmera, BSDF de materiais complexos, volumetria, convergência Monte Carlo ou saída de imagem. Portanto é um estágio de transporte, não um benchmark de qualidade de imagem.

Ambas as cargas são sintéticas, deterministicamente semeadas e não usam a topologia real da residência. Unidades de espaço arbitrárias, não metros da casa. O código funciona com a API `Embree 4.3.3` do Debian 13 e C++17/GCC, e não foi otimizado por máquina (`-march=x86-64`); linkagem exige `libtbb12`.

## Execução isolada no Linux, sem instalar pacotes no sistema

No Debian 13, se os pacotes forem do repositório oficial:

```sh
REPO="$(pwd)"  # execute a partir da raiz do repositório
mkdir -p /tmp/lightlab-debs /tmp/lightlab-root
cd /tmp/lightlab-debs
apt-get download libembree4-4 libembree-dev libtbb12 libtbbmalloc2
for deb in ./*.deb; do dpkg-deb -x "$deb" /tmp/lightlab-root; done
cd "$REPO"
PREFIX=/tmp/lightlab-root/usr
LIBDIR="$PREFIX/lib/x86_64-linux-gnu"
for name in embree_bench embree_photon_bench; do
  g++ -O3 -DNDEBUG -std=c++17 -march=x86-64 \
    -I"$PREFIX/include" "benchmarks/lighting_cpu/$name.cpp" \
    -L"$LIBDIR" -Wl,-rpath,"$LIBDIR" -lembree4 -o "/tmp/$name"
done
export LD_LIBRARY_PATH="$LIBDIR"
/tmp/embree_bench
/tmp/embree_photon_bench
```

No IFRO, o isolamento persistente do proprietário foi feito em `/var/lib/drosobot/lighting-lab`, sem `apt install` nem alteração dos drivers.

## Como comparar sem exagerar o resultado

- Executar pelo menos cinco rodadas com a mesma CPU, frequência, carga e versões; reportar mediana e dispersão. Separar *scene build* e *steady-state traversal*.
- Testar geometria estática e depois dinâmica; medir também CPU/RAM, latência de ponta a ponta da rede, tamanho do pacote e perda.
- Velocidade de interseção/s **não** equivale a qualidade fotorealista, ray/path/s de GPU moderna ou número de eventos que o Wi-Fi consegue distribuir.
- Para física completa, usar um renderizador de referência em executor externo (Mitsuba ou PBRT). O benchmark do IFRO informa a viabilidade de um integrador **leve** baseado em Embree; não prova que ele é o renderer universalmente mais rápido em 2026.
