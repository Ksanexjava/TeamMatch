/**
 * Ретранслятор Bot API Telegram на Cloudflare Workers.
 *
 * Зачем. Некоторые хостинги не выпускают исходящие соединения к api.telegram.org:
 * пакеты уходят и не возвращаются, бот падает с таймаутом. Этот скрипт принимает
 * запросы бота и пересылает их в Telegram со стороны Cloudflare, где блокировки нет.
 *
 * Как поставить.
 *   1. cloudflare.com → бесплатный аккаунт → Workers & Pages → Create → Worker.
 *   2. Вставить этот файл целиком вместо шаблона, заменить SECRET.
 *   3. Deploy. Адрес будет вида https://имя.поддомен.workers.dev
 *   4. На сервере в .env:  TELEGRAM_API_BASE=https://имя.поддомен.workers.dev/<SECRET>
 *
 * SECRET — первый сегмент пути, случайная строка (openssl rand -hex 16).
 * Без него запрос получает 404, иначе адрес стал бы открытым ретранслятором
 * к Telegram для любого, кто его найдёт.
 *
 * Важно понимать: TLS обрывается на стороне Cloudflare, то есть платформа видит
 * содержимое сообщений и токен бота. Это плата за обход блокировки. Нормально для
 * пилота, не нормально для продакшена с персональными данными — там меняют хостинг.
 */

const SECRET = "ЗАМЕНИ_МЕНЯ_НА_СЛУЧАЙНУЮ_СТРОКУ";
const UPSTREAM = "https://api.telegram.org";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);

    if (parts.shift() !== SECRET) {
      return new Response("Not found", { status: 404 });
    }

    const target = `${UPSTREAM}/${parts.join("/")}${url.search}`;
    const headers = new Headers(request.headers);
    // Host подставит сам fetch; чужой заголовок Telegram не нужен.
    headers.delete("Host");

    const noBody = request.method === "GET" || request.method === "HEAD";
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      // Запросы бота — небольшой JSON: читаем целиком, так надёжнее потока.
      body: noBody ? undefined : await request.arrayBuffer(),
    });

    return new Response(upstream.body, {
      status: upstream.status,
      headers: upstream.headers,
    });
  },
};
