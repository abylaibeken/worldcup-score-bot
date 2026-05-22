import asyncio
import csv
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

from sqlalchemy import (
    select,
    func,
    delete,
    update,
)

from bot.config import settings
from bot.db import init_db, async_session
from bot.models import User, Match, Prediction
from bot.scoring import calculate_points


dp = Dispatcher()

MATCHES_PER_PAGE = 10


main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📅 Матчи"),
            KeyboardButton(text="📝 Мои прогнозы"),
        ],
        [
            KeyboardButton(text="🏆 Таблица"),
        ],
    ],
    resize_keyboard=True,
)


async def show_matches_page(message_or_callback, page: int = 0):

    offset = page * MATCHES_PER_PAGE

    async with async_session() as session:

        result = await session.execute(
            select(Match)
            .where(Match.kickoff_at >= datetime.now())
            .order_by(Match.kickoff_at)
            .offset(offset)
            .limit(MATCHES_PER_PAGE)
        )

        matches_list = result.scalars().all()

        total_matches = await session.scalar(
            select(func.count(Match.id)).where(
                Match.kickoff_at >= datetime.now()
            )
        )

    if not matches_list:

        text = "Матчей на этой странице нет."

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⬅️ Назад",
                        callback_data=f"matches_page_{max(page - 1, 0)}",
                    )
                ]
            ]
        )

    else:

        total_pages = (
            total_matches + MATCHES_PER_PAGE - 1
        ) // MATCHES_PER_PAGE

        text = (
            f"Ближайшие матчи — "
            f"страница {page + 1}/{total_pages}:\n\n"
        )

        inline_keyboard = []

        for match in matches_list:

            date_text = match.kickoff_at.strftime(
                "%d.%m.%Y %H:%M"
            )

            text += (
                f"{match.id}. "
                f"{match.home_team} — {match.away_team}\n"
                f"{date_text}\n\n"
            )

            inline_keyboard.append(
                [
                    InlineKeyboardButton(
                        text=f"⚽ Прогноз на матч {match.id}",
                        callback_data=f"predict_match_{match.id}",
                    )
                ]
            )

        nav_buttons = []

        if page > 0:

            nav_buttons.append(
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data=f"matches_page_{page - 1}",
                )
            )

        if offset + MATCHES_PER_PAGE < total_matches:

            nav_buttons.append(
                InlineKeyboardButton(
                    text="➡️ Далее",
                    callback_data=f"matches_page_{page + 1}",
                )
            )

        if nav_buttons:
            inline_keyboard.append(nav_buttons)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=inline_keyboard
        )

    if isinstance(message_or_callback, CallbackQuery):

        await message_or_callback.message.edit_text(
            text,
            reply_markup=keyboard,
        )

        await message_or_callback.answer()

    else:

        await message_or_callback.answer(
            text,
            reply_markup=keyboard,
        )


@dp.message(Command("start"))
async def start(message: Message):

    async with async_session() as session:

        result = await session.execute(
            select(User).where(
                User.telegram_id == message.from_user.id
            )
        )

        user = result.scalar_one_or_none()

        if not user:

            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                full_name=message.from_user.full_name,
            )

            session.add(user)

            await session.commit()

    await message.answer(
        "Ты зарегистрирован в боте ЧМ-2026 ⚽",
        reply_markup=main_keyboard,
    )


@dp.message(Command("matches"))
async def matches(message: Message):
    await show_matches_page(message, page=0)


@dp.callback_query(lambda c: c.data.startswith("matches_page_"))
async def matches_page_callback(callback: CallbackQuery):

    page = int(callback.data.split("_")[-1])

    await show_matches_page(callback, page=page)


@dp.message(Command("predict"))
async def predict(message: Message):

    parts = message.text.split()

    if len(parts) != 3:

        await message.answer(
            "Формат:\n\n"
            "/predict 15 2:1"
        )

        return

    try:

        match_id = int(parts[1])

        pred_home, pred_away = map(
            int,
            parts[2].split(":"),
        )

    except ValueError:

        await message.answer(
            "Формат:\n\n"
            "/predict 15 2:1"
        )

        return

    async with async_session() as session:

        result = await session.execute(
            select(User).where(
                User.telegram_id == message.from_user.id
            )
        )

        user = result.scalar_one_or_none()

        if not user:

            await message.answer(
                "Сначала нажми /start"
            )

            return

        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )

        match = result.scalar_one_or_none()

        if not match:

            await message.answer(
                "Матч не найден."
            )

            return

        if datetime.now() >= match.kickoff_at:

            await message.answer(
                "Прогнозы на этот матч уже закрыты."
            )

            return

        result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.id,
                Prediction.match_id == match.id,
            )
        )

        existing_prediction = result.scalar_one_or_none()

        if existing_prediction:

            await message.answer(
                "Ты уже сделал прогноз "
                "на этот матч."
            )

            return

        prediction = Prediction(
            user_id=user.id,
            match_id=match.id,
            pred_home=pred_home,
            pred_away=pred_away,
        )

        session.add(prediction)

        await session.commit()

    await message.answer(
        f"Прогноз сохранён ✅\n\n"
        f"{match.home_team} — "
        f"{match.away_team}\n"
        f"{pred_home}:{pred_away}"
    )


@dp.callback_query(lambda c: c.data.startswith("predict_match_"))
async def predict_match_callback(callback: CallbackQuery):

    match_id = int(
        callback.data.split("_")[-1]
    )

    async with async_session() as session:

        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )

        match = result.scalar_one_or_none()

    if not match:

        await callback.message.answer(
            "Матч не найден."
        )

        await callback.answer()

        return

    if datetime.now() >= match.kickoff_at:

        await callback.message.answer(
            "Прогнозы на этот матч "
            "уже закрыты."
        )

        await callback.answer()

        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[]
    )

    for home in range(6):

        row = []

        for away in range(6):

            row.append(
                InlineKeyboardButton(
                    text=f"{home}:{away}",
                    callback_data=(
                        f"score_{match_id}_"
                        f"{home}_{away}"
                    ),
                )
            )

        keyboard.inline_keyboard.append(row)

    await callback.message.answer(
        f"{match.home_team} — "
        f"{match.away_team}\n\n"
        "Выбери прогноз:",
        reply_markup=keyboard,
    )

    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("score_"))
async def score_callback(callback: CallbackQuery):

    parts = callback.data.split("_")

    match_id = int(parts[1])
    pred_home = int(parts[2])
    pred_away = int(parts[3])

    async with async_session() as session:

        result = await session.execute(
            select(User).where(
                User.telegram_id == callback.from_user.id
            )
        )

        user = result.scalar_one_or_none()

        if not user:

            await callback.message.answer(
                "Сначала нажми /start"
            )

            await callback.answer()

            return

        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )

        match = result.scalar_one_or_none()

        if not match:

            await callback.message.answer(
                "Матч не найден."
            )

            await callback.answer()

            return

        if datetime.now() >= match.kickoff_at:

            await callback.message.answer(
                "Прогнозы на этот матч "
                "уже закрыты."
            )

            await callback.answer()

            return

        result = await session.execute(
            select(Prediction).where(
                Prediction.user_id == user.id,
                Prediction.match_id == match.id,
            )
        )

        existing_prediction = result.scalar_one_or_none()

        if existing_prediction:

            await callback.message.answer(
                "Ты уже сделал прогноз "
                "на этот матч."
            )

            await callback.answer()

            return

        prediction = Prediction(
            user_id=user.id,
            match_id=match.id,
            pred_home=pred_home,
            pred_away=pred_away,
        )

        session.add(prediction)

        await session.commit()

    await callback.message.answer(
        f"Прогноз сохранён ✅\n\n"
        f"{match.home_team} — "
        f"{match.away_team}\n"
        f"{pred_home}:{pred_away}"
    )

    await callback.answer()


@dp.message(Command("my"))
async def my_predictions(message: Message):

    async with async_session() as session:

        result = await session.execute(
            select(User).where(
                User.telegram_id == message.from_user.id
            )
        )

        user = result.scalar_one_or_none()

        if not user:

            await message.answer(
                "Сначала нажми /start"
            )

            return

        result = await session.execute(
            select(Prediction, Match)
            .join(
                Match,
                Prediction.match_id == Match.id
            )
            .where(
                Prediction.user_id == user.id
            )
            .order_by(Match.kickoff_at)
        )

        rows = result.all()

    if not rows:

        await message.answer(
            "У тебя пока нет прогнозов."
        )

        return

    text = "Мои прогнозы:\n\n"

    for prediction, match in rows:

        result_text = "матч ещё не сыгран"

        if (
            match.home_score is not None
            and match.away_score is not None
        ):
            result_text = (
                f"{match.home_score}:"
                f"{match.away_score}"
            )

        text += (
            f"{match.home_team} — "
            f"{match.away_team}\n"
            f"Прогноз: "
            f"{prediction.pred_home}:"
            f"{prediction.pred_away}\n"
            f"Результат: {result_text}\n"
            f"Очки: {prediction.points}\n\n"
        )

    await message.answer(text)


async def import_matches_from_csv():

    csv_path = Path("matches.csv")

    if not csv_path.exists():
        return 0

    added_count = 0

    async with async_session() as session:

        with csv_path.open(
            "r",
            encoding="utf-8"
        ) as file:

            reader = csv.DictReader(file)

            for row in reader:

                home_team = row[
                    "home_team"
                ].strip()

                away_team = row[
                    "away_team"
                ].strip()

                kickoff_at = datetime.strptime(
                    row["kickoff_at"].strip(),
                    "%Y-%m-%d %H:%M",
                )

                result = await session.execute(
                    select(Match).where(
                        Match.home_team == home_team,
                        Match.away_team == away_team,
                        Match.kickoff_at == kickoff_at,
                    )
                )

                existing_match = (
                    result.scalar_one_or_none()
                )

                if existing_match:
                    continue

                match = Match(
                    home_team=home_team,
                    away_team=away_team,
                    kickoff_at=kickoff_at,
                )

                session.add(match)

                added_count += 1

        await session.commit()

    return added_count


@dp.message(Command("import_matches"))
async def import_matches(message: Message):

    if message.from_user.id not in settings.admin_ids:

        await message.answer(
            "Эта команда только для админа."
        )

        return

    added_count = await import_matches_from_csv()

    await message.answer(
        f"Импорт завершён.\n"
        f"Добавлено матчей: {added_count}"
    )


@dp.message(Command("result"))
async def set_result(message: Message):

    if message.from_user.id not in settings.admin_ids:

        await message.answer(
            "Эта команда только для админа."
        )

        return

    parts = message.text.split()

    if len(parts) != 3:

        await message.answer(
            "Формат:\n"
            "/result 15 2:1"
        )

        return

    try:

        match_id = int(parts[1])

        real_home, real_away = map(
            int,
            parts[2].split(":"),
        )

    except ValueError:

        await message.answer(
            "Формат:\n"
            "/result 15 2:1"
        )

        return

    async with async_session() as session:

        result = await session.execute(
            select(Match).where(
                Match.id == match_id
            )
        )

        match = result.scalar_one_or_none()

        if not match:

            await message.answer(
                "Матч не найден."
            )

            return

        match.home_score = real_home
        match.away_score = real_away
        match.status = "finished"

        result = await session.execute(
            select(Prediction).where(
                Prediction.match_id == match.id
            )
        )

        predictions = result.scalars().all()

        for prediction in predictions:

            prediction.points = calculate_points(
                prediction.pred_home,
                prediction.pred_away,
                real_home,
                real_away,
            )

        result = await session.execute(
            select(User)
        )

        users = result.scalars().all()

        for user in users:

            result = await session.execute(
                select(Prediction).where(
                    Prediction.user_id == user.id
                )
            )

            user_predictions = (
                result.scalars().all()
            )

            user.points = sum(
                p.points
                for p in user_predictions
            )

        await session.commit()

    await message.answer(
        f"Результат сохранён ✅\n\n"
        f"{match.home_team} — "
        f"{match.away_team}\n"
        f"{real_home}:{real_away}"
    )


@dp.message(Command("stats"))
async def stats(message: Message):

    if message.from_user.id not in settings.admin_ids:

        await message.answer(
            "Эта команда только для админа."
        )

        return

    async with async_session() as session:

        users_count = await session.scalar(
            select(func.count(User.id))
        )

        predictions_count = await session.scalar(
            select(func.count(Prediction.id))
        )

        matches_count = await session.scalar(
            select(func.count(Match.id))
        )

        finished_matches_count = await session.scalar(
            select(func.count(Match.id)).where(
                Match.status == "finished"
            )
        )

    await message.answer(
        "Статистика бота:\n\n"
        f"Пользователей: {users_count}\n"
        f"Прогнозов: {predictions_count}\n"
        f"Матчей: {matches_count}\n"
        f"Завершённых матчей: "
        f"{finished_matches_count}"
    )


@dp.message(Command("table"))
async def table(message: Message):

    async with async_session() as session:

        result = await session.execute(
            select(User).order_by(
                User.points.desc()
            )
        )

        users = result.scalars().all()

    if not users:

        await message.answer(
            "Таблица пока пустая."
        )

        return

    text = "Таблица лидеров:\n\n"

    for index, user in enumerate(
        users,
        start=1,
    ):

        name = (
            user.full_name
            or user.username
            or str(user.telegram_id)
        )

        text += (
            f"{index}. "
            f"{name} — "
            f"{user.points} очков\n"
        )

    await message.answer(text)


@dp.message(Command("reset_predictions"))
async def reset_predictions(message: Message):

    if message.from_user.id not in settings.admin_ids:

        await message.answer(
            "Эта команда только для админа."
        )

        return

    async with async_session() as session:

        await session.execute(
            delete(Prediction)
        )

        await session.execute(
            update(User).values(
                points=0
            )
        )

        await session.execute(
            update(Match).values(
                home_score=None,
                away_score=None,
                status="scheduled",
            )
        )

        await session.commit()

    await message.answer(
        "Прогнозы удалены.\n"
        "Очки обнулены.\n"
        "Матчи снова scheduled."
    )


@dp.message(Command("reset_all"))
async def reset_all(message: Message):

    if message.from_user.id not in settings.admin_ids:

        await message.answer(
            "Эта команда только для админа."
        )

        return

    async with async_session() as session:

        await session.execute(
            delete(Prediction)
        )

        await session.execute(
            delete(Match)
        )

        await session.execute(
            delete(User)
        )

        await session.commit()

    await message.answer(
        "База полностью очищена:\n"
        "- пользователи удалены\n"
        "- матчи удалены\n"
        "- прогнозы удалены"
    )


@dp.message(lambda message: message.text == "📅 Матчи")
async def matches_button(message: Message):
    await matches(message)


@dp.message(lambda message: message.text == "📝 Мои прогнозы")
async def my_button(message: Message):
    await my_predictions(message)


@dp.message(lambda message: message.text == "🏆 Таблица")
async def table_button(message: Message):
    await table(message)


async def main():

    await init_db()

    bot = Bot(
        token=settings.bot_token
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())