# 0007 — Contas de farm com e-mail e senha; senhas fora do worker

- **Status:** Aceita
- **Data:** 2026-11-11
- **Altera:** [0006](0006-contas.md), no ponto "cada conta tem a própria conta Google"

## Contexto

O plano original era cada conta de farm ter a própria conta Google, o que exige criar e manter 3 contas Google. A alternativa considerada foi criar as contas de farm com e-mail e senha e guardar usuário e senha no `.env` para o worker logar sozinho.

Pontos levantados:
- Os Termos (seção 8) dizem que o cadastro, o login e o "Esqueci minha senha" passam pelo **Cloudflare Turnstile** (anti-robô). Um login automatizado esbarra nele, e contorná-lo seria burlar uma proteção do jogo, o que a seção 5 proíbe nas automações.
- O token de sessão dura cerca de 30 dias e é renovado pelo servidor com `sessao.renovada` (ver [protocolo.md](../protocolo.md)). Com o worker salvando o token renovado, o login manual quase nunca é necessário.

## Decisão

- As **3 contas de farm** são criadas com **e-mail e senha**, não com Google. Vale testar aliases do mesmo Gmail (`email+farm1@gmail.com`), se o jogo aceitar o `+`.
- A **conta pessoal** continua com login pelo Google.
- As **senhas ficam num gerenciador de senhas** (Bitwarden, 1Password ou outro). Elas **não** vão para o `.env`, o banco nem o droplet.
- O worker recebe só `nick`, `token` e `dispositivo` de cada conta, e atualiza o token sempre que chega um `sessao.renovada`.
- O login é sempre manual, no navegador (o Turnstile aparece para a pessoa, como para qualquer jogador). O worker **nunca** tenta logar com senha.

## Consequências

- Não é preciso criar nem manter 3 contas Google.
- Se o droplet ou o banco vazarem, o atacante leva tokens, não senhas. Para cortar o acesso, basta trocar a senha da conta no jogo.
- Quando um token morre, o painel mostra `needs_login`. Aí é logar na mão, extrair o token (ver o passo a passo em [protocolo.md](../protocolo.md)) e atualizar.
- A frequência do login manual depende de o worker salvar direito os tokens renovados. Isso vira requisito da fase 2.

## Alternativas consideradas

- **Usuário e senha no `.env`, com login automatizado:** rejeitada. Exigiria contornar o Turnstile (proibido pelos termos) e deixaria as senhas expostas no servidor.
- **Uma conta Google por conta de farm:** funciona, mas dá mais trabalho e não traz ganho em relação ao e-mail e senha.
