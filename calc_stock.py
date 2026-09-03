import pandas as pd
from pathlib import Path
from datetime import timedelta

PATH_SOURCE = Path(__file__).parent
PATH_STOCK = PATH_SOURCE / 'stock'
PATH_TRANS = PATH_SOURCE / 'invent_trans'

def main() -> None:
    # 1. Начальный остаток
    # stock_file = list(PATH_STOCK.glob('stock_*.csv'))
    stock_file = PATH_STOCK / 'stock_2025_04_30.csv'
    df_initial = pd.read_csv(stock_file, sep=';', parse_dates=['trans_date'])
    # Нормализация времени(были ошибки при сравнении)
    df_initial['trans_date'] = df_initial['trans_date'].dt.normalize()
    initial_date = df_initial['trans_date'].iloc[0]  # это Timestamp

    df_initial = df_initial[['item_id', 'location_id', 'qty', 'cost_amount']].copy()

    # 2. Файлы с транзакциями
    trans_files = list(PATH_TRANS.glob('invent_trans_*.csv'))
    if not trans_files:
        print('Нет файлов транзакций.')
        return

    # Одна таблица
    df_trans = pd.concat(
        [pd.read_csv(f, sep=';', parse_dates=['trans_date']) for f in trans_files],
        ignore_index=True
    )
    df_trans['trans_date'] = df_trans['trans_date'].dt.normalize()

    # Фильтруем транзакции после начальной даты
    df_trans = df_trans[df_trans['trans_date'] > initial_date].copy()
    if df_trans.empty:
        print('Нет транзакций после начальной даты.')
        return

    # Создаём столбец date (одинаковый тип). Без этого выпадала ошибка при агрегации
    df_trans['date'] = df_trans['trans_date']

    # 3. Агрегация по дням
    df_daily = df_trans.groupby(
        ['item_id', 'location_id', 'date'],
        as_index=False
    ).agg({
        'qty': 'sum',
        'cost_amount': 'sum'
    })

    # 4. Все пары (item_id, location_id)
    all_pairs = pd.Index(df_initial[['item_id', 'location_id']].drop_duplicates()).union(
        df_daily[['item_id', 'location_id']].drop_duplicates()
    )
    all_pairs = pd.DataFrame(list(all_pairs), columns=['item_id', 'location_id'])

    # 5. Сетка всех дней (от начальной+1 до максимальной даты в транзакциях)
    max_date = df_daily['date'].max()
    date_range = pd.date_range(start=initial_date + timedelta(days=1), end=max_date, freq='D')

    # Декартово произведение пар-значений и листа дат
    full_grid = all_pairs.assign(key=1).merge(
        pd.DataFrame({'date': date_range, 'key': 1}), on='key'
    ).drop('key', axis=1)

    # Явно приводим дату к тому же типу
    full_grid['date'] = pd.to_datetime(full_grid['date']).dt.normalize()

    # 6. Добавляем ежедневные изменения
    full_grid = full_grid.merge(df_daily, on=['item_id', 'location_id', 'date'], how='left')
    full_grid['qty'] = full_grid['qty'].fillna(0)
    full_grid['cost_amount'] = full_grid['cost_amount'].fillna(0)

    # 7. Добавляем начальные остатки
    full_grid = full_grid.merge(df_initial, on=['item_id', 'location_id'], how='left', suffixes=('', '_init'))
    full_grid['qty_init'] = full_grid['qty_init'].fillna(0)
    full_grid['cost_amount_init'] = full_grid['cost_amount_init'].fillna(0)

    # 8. Кумулятивные суммы
    full_grid = full_grid.sort_values(['item_id', 'location_id', 'date'])
    full_grid['cum_qty'] = full_grid.groupby(['item_id', 'location_id'])['qty'].cumsum()
    full_grid['cum_cost'] = full_grid.groupby(['item_id', 'location_id'])['cost_amount'].cumsum()

    full_grid['closing_qty'] = full_grid['qty_init'] + full_grid['cum_qty']
    full_grid['closing_cost'] = full_grid['cost_amount_init'] + full_grid['cum_cost']

    # 9. Итоговая печать
    last_day = full_grid[full_grid['date'] == max_date]
    out_data = last_day[['item_id', 'location_id', 'closing_qty', 'closing_cost']].copy()
    out_data.rename(columns={'closing_qty': 'qty', 'closing_cost': 'cost_amount'}, inplace=True)
    out_file = PATH_STOCK / f'stock_{max_date.strftime("%Y_%m_%d")}.csv'
    out_data.to_csv(out_file, sep=';', index=False, float_format='%.6f', date_format='%Y-%m-%d')
    print(f'Создан {out_file.name}')

    print('Выполнено !')


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print('Oops... Something wrong!')
        print(e)