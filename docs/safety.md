# Política mínima de segurança

1. Somente comandos explicitamente enumerados em allowlist; nenhum shell genérico exposto ao robô.
2. Nenhuma movimentação física não supervisionada nesta etapa.
3. `stop` local e timeout de comando obrigatórios antes de qualquer teste de locomoção.
4. Atuação gradual e com limites de duração, frequência, amplitude e estado de bateria.
5. Falha de rede => parar ou permanecer em estado seguro, nunca continuar indefinidamente.
6. Dados de rede doméstica, BSSID real, tokens, credenciais e capturas privadas não são publicados.
7. Nunca inferir posição efetiva das pernas a partir apenas de ângulo comandado.
8. Alterações de firmware exigem backup, identificação da placa, plano de recuperação e autorização específica.
