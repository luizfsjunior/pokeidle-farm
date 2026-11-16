# Painel: perfil da conta, imagens e visual novo (16/11/2026)

## Problema

O painel só mostrava métricas por hora. Nível, ouro, gemas, diamantes, equipe, coleção e mochila
existem no `estado` do jogo, mas só ficavam gravados no `state.snapshot` de cada conexão. Esse snapshot
envelhece em minutos: o ouro muda a cada abate e a equipe muda a cada `pkMud`.

## Decisão

1. **Worker, plugin `profile` (sempre ligado).** Ele assina `state.snapshot` e `state.patch` e junta o
   estado em `profile.ProfileState`:
   - o welcome substitui tudo;
   - `pkMud` faz merge por `id` e `pkFora` remove;
   - `dexMud` faz merge na Pokédex;
   - `items` e `balls` fazem merge;
   - os outros campos substituem o valor anterior.

   A cada `interval_s` (120 s), e só se algo mudou, ele grava **uma linha por conta** em
   `account_profile`. O primeiro welcome grava na hora. Se o banco falhar, tenta de novo no próximo
   intervalo, e grava também ao parar. Não manda nada ao jogo.
2. **Tabela `account_profile`** (migration `20261116020000`). Guarda os números da conta e a equipe
   (pokémons com `slot`). Da coleção guarda os 24 mais fortes e até 60 shinies. Guarda também os mapas de
   itens e bolas e `estado_keys`, que tem só os *nomes* dos campos do estado, para descobrir o que mais dá
   para mostrar. O RLS deixa cada dono só ler. A escrita é só da service_role.
3. **Ícone dos itens.** `game_items.icon` vem do `icon` do `items.json` e do `itensNossos`. O welcome sem
   ícone não apaga o ícone que já está gravado.
4. **Imagens do jogo.**
   - Os retratos vêm do atlas público `assets/site/assets/maps/marker-atlas.json` e do PNG dele,
     indexados por `looktype`. O looktype sai do pokémon ou, se não vier, de `game_species.data.looktype`.
   - O servidor do painel relê o JSON a cada 5 min, porque o jogo troca o atlas a cada atualização. A
     imagem leva `?v=`.
   - Sem atlas aparece uma pokébola em CSS. Item sem ícone mostra as iniciais.
   - É o mesmo esquema do pokeidle-manager-online.
5. **Visual.**
   - Cada conta é um "cartão de treinador": o pokémon ativo sobre um tufo de grama, o nick em fonte
     pixel (Silkscreen, o único lugar com ela), nível com barra de XP, a carteira (ouro, gemas e
     diamantes, cada um com cor e forma próprias), a faixa da equipe e, na visão geral, os números de hoje.
   - O corpo usa Onest. Fundo cinza-azulado frio.
   - A página da conta ganha Equipe (HP, IV, nota, poder), Coleção e Mochila.

## Campos do jogo usados (a confirmar com uma conta real)

`level`, `xp`, `xpNivel`, `xpProximo`, `gold`, `orbs` (gemas), `diamonds`, `loja.vipAte`, `huntSlug`,
`activeId`, `pokemons[]` (`id`, `speciesId`, `nome`, `level`, `shiny`, `slot`, `looktype`, `poder`,
`quality`, `potencia`, `hp`, `maxHp`, `ivs`), `pokedex`/`dexMud` (`c` = capturas), `items` e `balls`.

Os nomes vêm do mapeamento do pokeidle-manager-online. O que vier com outro nome aparece em branco ("—")
e não quebra nada. Para conferir, rode no SQL Editor (só leitura):
`select estado_keys from account_profile`.
