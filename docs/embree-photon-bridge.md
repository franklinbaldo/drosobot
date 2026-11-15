# Ponte Embree → DPH1 → receptor Rust (primeira integração executável)

## O que é, e o que não é

A fonte `benchmarks/lighting_cpu/embree_photon_events.cpp` executa interseções **reais em 3D** com o motor Intel Embree 4 (`rtcIntersect1`). O cenário é **sintético**: duas caixas de 2 × 2 × 2 m a partir de (2,2,0) e (6,4,0), numa sala lógica de 10 × 8 m. O emissor dispara oito raios cardinais no plano horizontal z=1 m. O primeiro contato em cada raio produz uma amostra que é codificada como evento DPH1.

- **Fonte/avaliador** conhecem o objeto atingido, normal e coordenadas; o receptor de eventos não recebe a lista de caixas.
- O protocolo DPH1 antigo é preservado: `Epoch`, `Emitted`, `Contact`, com **17 eventos / 712 bytes** para os oito raios.
- O emissor calcula interseções 3D em Embree; os eventos DPH1 são **projetados em 2D**, com velocidades de 1 m/tick. A altura permanece fixa em 1 m. Não são fótons físicos, renderização de câmera, iluminação global de materiais complexos, nem uma medição de Wi-Fi.
- O receptor `rust/drosobot-sim/src/bin/photon_embree_ingest.rs` lê um registro DPH1 de arquivo local com tamanho limitado, rejeita registros truncados e compara **no avaliador** os 17 eventos e duas superfícies contra o oráculo sintético Rust já existente. Assim a correspondência é de **contrato determinístico para um cenário**, não uma comparação estatística de renders.
- Os rótulos semânticos `object_id` continuam presentes em DPH1. **Não afirmar que este é um teste sem rótulos**, apesar de o receptor só conhecer eventos e não o mapa integral.

## Execução no IFRO

As bibliotecas `libembree4.so.4` (Debian 13, versão 4.3.3) e `libtbb.so.12` já foram baixadas de pacotes oficiais e extraídas em `/var/lib/drosobot/lighting-lab/embree-root/`, sem instalação global nem reinício de serviços. A compilação usa `g++ -O3 -march=x86-64`, sem AVX2. Um teste inicial no IFRO produziu os 17 eventos e 712 bytes, com **100 mil consultas adicionais em aproximadamente 16,3 ms** na cena de duas caixas. Não interpretar a taxa desse microbenchmark como taxa de renderização integral ou largura de banda de rede.

Para compilar e gerar outro registro em arquivo novo (sempre respeitando a reserva de RAM/CPU do IFRO):

```sh
cd /opt/drosobot
LAB=/var/lib/drosobot/lighting-lab
EMBREE="$LAB/embree-root/usr"
LIBDIR="$EMBREE/lib/x86_64-linux-gnu"
g++ -std=c++17 -O3 -DNDEBUG -march=x86-64 -I"$EMBREE/include" \
  benchmarks/lighting_cpu/embree_photon_events.cpp \
  -L"$LIBDIR" -Wl,-rpath,"$LIBDIR" -lembree4 \
  -o "$LAB/benchmarks/embree_photon_events"
export LD_LIBRARY_PATH="$LIBDIR"
"$LAB/benchmarks/embree_photon_events" --output "$LAB/benchmarks/NEW_JOURNAL.dph1"
```

O comando falha se o arquivo de saída já existir ou for link simbólico. Os arquivos de registro ficam **somente no IFRO ou no workspace privado**; não são necessários para compilar/testar um cliente público. Nunca executar o binário no ESP32 ou permitir que esses eventos controlem servos. Para replay pela interface Rust, usar o binário `photon_embree_ingest` compilado pelo GitHub Actions, não compilar Rust pesado no IFRO.

## Gate em GitHub Actions

O job `embree-bridge` em `.github/workflows/test.yml` constrói C++ com Embree 4 e Rust em runner externo; gera o registro, roda o receptor, confere a reconstrução e valida um teste negativo com byte alterado. Publica artefatos nativos Linux amd64 com checksums para que o IFRO possa executá-los **sem compilação local de Rust**.

## Próximos experimentos de maior informação

1. Remover realmente o campo `object_id` **do protocolo em trânsito**, criando uma versão DPH2 e um agrupador não supervisionado, com teste de ambiguidade/abstinência.
2. Registrar eventos multi-bounce em 3D com energia e tempo óptico, uma versão explícita do protocolo e oráculo quantitativo externo.
3. Transmitir uma amostra compactada por HTTP/SSE na LAN da Tenda, com **receptor independente** no navegador de um celular, medindo perda, RTT e frescura da reconstrução. Não usar tempo de Wi-Fi como distância física sem Wi-Fi RTT/FTM validado.
4. Medir limites de bytes/s e descartar/amostrar eventos de baixa informação antes de transmitir. Um kernel de milhões de consultas/s é muito mais rápido do que a capacidade prática de transportar milhões de eventos completos por segundo.

**Segurança:** sem escanear ou alterar a Tenda; serviço Xiaozhi e controle motor do ESP-Hi continuam independentes. Antes de expor um servidor na LAN, implementar somente endpoints GET restritos e limites explícitos; não reutilizar credenciais domésticas.
