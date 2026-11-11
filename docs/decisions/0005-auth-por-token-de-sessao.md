# 0005 — Auth no jogo por token de sessão reaproveitado

- **Status:** Proposta. Depende de validar na fase 1.
- **Data:** 2026-11-11

## Contexto

As contas entram pelo Google. O login do jogo passa pelo Cloudflare Turnstile (anti-robô), e o login com Google em navegador automatizado costuma cair em captcha. Os termos dizem que o token da sessão fica no localStorage.

## Decisão (proposta)

- O login é feito na mão, no navegador, uma vez por conta.
- O token de sessão é copiado do localStorage e guardado criptografado em `account_tokens`, ou no `.env` durante o desenvolvimento.
- O worker usa o token no handshake do WebSocket.
- Quando o token expira, a conta vira `needs_login` e o painel avisa.

## Consequências

- Não é preciso automatizar o login nem contornar o Turnstile.
- Tem uma etapa manual periódica, com frequência ainda desconhecida: depende de quanto o token dura.
- O token é uma credencial e nunca vai para o repositório.

## A validar

Respostas iniciais vindas do código do [DiuleJR/pokeidle-manager-online](https://github.com/DiuleJR/pokeidle-manager-online), ainda a confirmar por nós. Detalhes em [protocolo.md](../protocolo.md).

- [x] Nome da chave no localStorage: `sessao` (JSON com `nick` e `token`), mais `id-dispositivo`
- [x] Como o token vai no handshake: na primeira mensagem, `{t: "hello", nick, token, delta: 1, dispositivo}`
- [x] Tempo de expiração: cerca de 30 dias. O servidor manda `sessao.renovada` com o token novo, que precisa ser salvo
- [x] Mesmo token em dois lugares: derruba o outro (close 4001). Não abrir a conta de farm no navegador com o worker ligado
- [ ] Confirmar tudo acima no DevTools com uma conta nossa

## Consequência extra

O `account_tokens` precisa guardar também o `dispositivo` de cada conta, e o worker precisa atualizar o token sempre que chegar um `sessao.renovada`.
