# Primeiro ensaio MaleCNS verdadeiro: observação neural em paralelo

**Não é um robô controlado pela mosca.** Esta etapa executa o operador recorrente congelado derivado do MaleCNS v1.0, **mas as ações na grade sintética continuam sendo escolhidas pelo `ReactiveBaseline` convencional**. O objetivo é estabelecer o carregamento, a proveniência e o primeiro caminho das observações permitidas até as populações neurais, sem fazer alegações de competência motora.

## Dados e identidade

Os dados vêm do projeto público [FlyDoom](https://github.com/franklinbaldo/franklinbaldo.github.io), sem gerar cassetes ou grafos artificiais em substituição ao conectoma quando o artefato existe:

- `public/flydoom/malecns_l3_compact.mcns` SHA-256: `92a821dfbaed40fd124c9b6d9d32ee68830d2659e761c355b8340103d8d616fd`.
- `public/flydoom/malecns_circuit.json` SHA-256: `8bf1ed9f2509768472d031852bb3645bdedf8dd481beecf95c74c957f74dabae`.
- O filtro `status == Traced` das anotações de referência produziu 165.122 índices; o grafo compacto traz 1.542.657 conexões. As populações usadas pelo ensaio são `vpl=4589`, `vpr=4612`, `dnl=656`, `dnr=648`.
- O formato CSR/FlatBuffer e a função de relaxamento (`0.65 * state + 0.35 * tanh(weighted_sum * scale * 3.5 + drive)`) foram portados do [sim.js original](https://github.com/franklinbaldo/franklinbaldo.github.io/blob/main/public/fly-shader/sim.js). A dinâmica é uma escolha computacional explícita, não um modelo validado de todos os mecanismos fisiológicos.

O script `scripts/prepare_malecns.py` baixa os artefatos públicos, rejeita qualquer mudança de hash e escreve somente em diretórios locais ignorados pelo Git. Nenhum arquivo de dados da casa, chave ou token é exigido.

## Experimento

1. `reference_world()` fornece a mesma sequência sintética de observações ao controlador convencional e a dois observadores neurais.
2. Uma transdução artificial explícita recebe `ahead.blocked`: excita `vpl=0.8/vpr=0.1` se bloqueado, e `vpl=0.1/vpr=0.8` se livre. **Não** é visão biológica, propriocepção nem sensores do ESP-Hi.
3. O grafo **original** é atualizado por 25 ticks, com médias dos grupos `dnr` e `dnl` em cada tick.
4. O controle negativo mantém linhas, pesos, orçamento e entrada iguais, mas aplica uma permutação bijetiva global às colunas das conexões (`(3*column + 17) mod 165122`). Isto é uma *permutação de rótulos-alvo*, não um controle de religação que preserve explicitamente todos os graus ou a anatomia. Sua interpretação é exploratória.
5. As ações físicas **não existem** no ensaio. O `ReactiveBaseline` convencional escolhe todos os comandos da grade nas duas condições. O circuito neural só observa e produz diferenças de atividade.
6. O relatório em CI apresenta energia média da diferença lateral `dnr-dnl`, variação entre os modelos e segurança da simulação. Nenhuma superioridade é inferida de uma diferença não zero.

## Reproduzir

```sh
python3 scripts/prepare_malecns.py --output .research/malecns-verified
cargo test --manifest-path rust/drosobot-sim/Cargo.toml --all-targets
cargo run --release --manifest-path rust/drosobot-sim/Cargo.toml --bin malecns-probe -- .research/malecns-verified/connectome.mcns .research/malecns-verified/ports.txt
```

As etapas compiladas são executadas pelo GitHub Actions; não é necessário compilar no IFRO. O artefato do conectoma **não** é anexado ao repositório DrosoBot.

## Próxima condição científica

Antes de chamar qualquer resultado de controle MaleCNS será necessário: (i) um decodificador de saída declarado **antes** da avaliação, (ii) efetiva influência da atividade neural na escolha da ação, (iii) avaliações fora de amostra, (iv) comparações de orçamento pareado com controladores convencionais e redes nulas, (v) controles anatômicos de portas de entrada/saída, (vi) várias sementes e intervalos de incerteza. Somente mais adiante teremos medições físicas admissíveis do robô. A própria literatura interna distingue [observador, operador e controlador](https://github.com/franklinbaldo/papers/blob/main/research/malecns-role-registry.md).
