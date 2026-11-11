# Protocolo WebSocket do pokeidle.io

> 🔴 Ainda não mapeado. Este é o entregável da fase 1 do [roadmap](roadmap.md).

## Como mapear

1. Abra https://pokeidle.io/app com o DevTools aberto (F12).
2. Vá em Network → filtro **WS** → selecione a conexão → aba **Messages**.
3. Anote, para cada tipo de mensagem: direção (cliente→servidor ou servidor→cliente), nome ou tipo, campos e um exemplo **sem dados sensíveis**.
4. Compare com projetos da comunidade que já fazem isso, como o [DiuleJR/pokeidle-manager-online](https://github.com/DiuleJR/pokeidle-manager-online) (headless em Python) e o [Romeu-q/ThoseIdles](https://github.com/Romeu-q/ThoseIdles), que menciona as mensagens `hello` e `ping`.

> ⚠️ Nunca cole aqui tokens, cookies ou mensagens com dados de conta. O repositório é público.

## Conexão

| Item | Valor |
|---|---|
| URL | _a descobrir_ |
| Auth no handshake | _a descobrir_ (token do localStorage?) |
| Heartbeat | _a descobrir_ (`ping`?) |

## Mensagens cliente → servidor

| Tipo | Campos | Uso | Exemplo |
|---|---|---|---|
| `hello` | _?_ | início da sessão | |
| `ping` | _?_ | heartbeat | |

## Mensagens servidor → cliente

| Tipo | Campos | Uso | Exemplo |
|---|---|---|---|

## Ações de jogo relevantes

- [ ] Trocar de hunt
- [ ] Comprar item na loja (bolas, poções, revives)
- [ ] Usar item
- [ ] Ler inventário
- [ ] Anunciar no Mercado
- [ ] Ler anúncios do Mercado
