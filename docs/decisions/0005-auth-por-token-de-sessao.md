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

- [ ] Nome da chave do token no localStorage
- [ ] Como o token vai no handshake (query string, primeira mensagem, header?)
- [ ] Tempo de expiração
- [ ] Se usar o mesmo token em dois lugares ao mesmo tempo derruba uma das sessões
