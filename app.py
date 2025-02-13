from flask import Flask, render_template, request, jsonify, send_file
import sqlite3
from datetime import datetime, timedelta
import hashlib
import random
import os
import requests
import subprocess



app = Flask(__name__)

# Configuração do repositório do GitHub
GITHUB_USERNAME = "klauszoares"
GITHUB_REPO = "painel"
GITHUB_BRANCH = "main"
GITHUB_TOKEN = "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"

# URL do banco de dados no GitHub
GITHUB_DB_URL = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/events.db"

# Se o banco não existir localmente, baixar do GitHub
if not os.path.exists("events.db"):
    response = requests.get(GITHUB_DB_URL)
    if response.status_code == 200:
        with open("events.db", "wb") as f:
            f.write(response.content)
    else:
        print("Banco de dados não encontrado no GitHub. Criando um novo.")

# Conectar ao SQLite
conn = sqlite3.connect("events.db", check_same_thread=False)
cursor = conn.cursor()




@app.route('/ping')
def ping():
    return "pong", 200


# Criar tabela corrigida com nova coluna "repeat_weekly"
def recreate_table():
    cursor.execute('''CREATE TABLE IF NOT EXISTS events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        start TEXT,
                        end TEXT,
                        repeat_weekdays INTEGER DEFAULT 0,
                        repeat_monthly INTEGER DEFAULT 0,
                        repeat_weekly INTEGER DEFAULT 0,
                        color TEXT DEFAULT '#3498db') -- Cor padrão para eventos
                   ''')
    conn.commit()

recreate_table()

# Função para salvar o banco de dados no GitHub
def save_db_to_github():
    try:
        subprocess.run(["git", "add", "events.db"])
        subprocess.run(["git", "commit", "-m", "Atualizando banco de dados"])
        subprocess.run(["git", "push", "origin", "main"])
    except Exception as e:
        print(f"Erro ao salvar no GitHub: {e}")

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/get_events')
def get_events():
    cursor.execute("SELECT id, title, start, end, repeat_weekdays, repeat_monthly, repeat_weekly, color FROM events")
    events = []

    for row in cursor.fetchall():
        event = {
            "id": row[0],
            "title": row[1],
            "start": row[2],
            "end": row[3],
            "repeatWeekdays": bool(row[4]),
            "repeatMonthly": bool(row[5]),
            "repeatWeekly": bool(row[6]),
            "color": row[7]
        }

        events.append(event)

        # Criar eventos dinâmicos sem armazenar no banco
        original_date = datetime.strptime(row[2][:10], "%Y-%m-%d")

        for i in range(1, 365):
            new_date = original_date + timedelta(days=i)
            new_date_str = new_date.strftime("%Y-%m-%d")

            if event["repeatWeekdays"] and new_date.weekday() < 5:
                events.append({
                    "id": f"{row[0]}-weekdays-{i}",
                    "title": event["title"],
                    "start": new_date_str + row[2][10:],
                    "end": new_date_str + row[3][10:],
                    "color": event["color"]
                })

            if event["repeatMonthly"] and new_date.day == original_date.day:
                events.append({
                    "id": f"{row[0]}-monthly-{i}",
                    "title": event["title"],
                    "start": new_date_str + row[2][10:],
                    "end": new_date_str + row[3][10:],
                    "color": event["color"]
                })

            if event["repeatWeekly"] and new_date.weekday() == original_date.weekday():
                events.append({
                    "id": f"{row[0]}-weekly-{i}",
                    "title": event["title"],
                    "start": new_date_str + row[2][10:],
                    "end": new_date_str + row[3][10:],
                    "color": event["color"]
                })

    return jsonify(events)


@app.route('/add_event', methods=['POST'])
def add_event():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Dados inválidos"}), 400

    title = data['title']
    start_time = data['start']
    end_time = data['end']
    repeat_weekdays = int(data.get('repeatWeekdays', False))
    repeat_monthly = int(data.get('repeatMonthly', False))
    repeat_weekly = int(data.get('repeatWeekly', False))

    cursor.execute("SELECT color FROM events WHERE title = ?", (title,))
    result = cursor.fetchone()
    if result:
        color = result[0]
    else:
        color = generate_fixed_color(title)

    try:
        cursor.execute("INSERT INTO events (title, start, end, repeat_weekdays, repeat_monthly, repeat_weekly, color) VALUES (?, ?, ?, ?, ?, ?, ?)",
                       (title, start_time, end_time, repeat_weekdays, repeat_monthly, repeat_weekly, color))
        conn.commit()

        original_date = datetime.strptime(start_time[:10], "%Y-%m-%d")

        # Criar eventos repetidos
        for i in range(1, 365):
            new_date = original_date + timedelta(days=i)
            new_date_str = new_date.strftime("%Y-%m-%d")

            if repeat_weekdays and new_date.weekday() < 5:
                cursor.execute("INSERT INTO events (title, start, end, repeat_weekdays, repeat_monthly, repeat_weekly, color) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, new_date_str + start_time[10:], new_date_str + end_time[10:], repeat_weekdays, repeat_monthly, repeat_weekly, color))

            if repeat_monthly and new_date.day == original_date.day:
                cursor.execute("INSERT INTO events (title, start, end, repeat_weekdays, repeat_monthly, repeat_weekly, color) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, new_date_str + start_time[10:], new_date_str + end_time[10:], repeat_weekdays, repeat_monthly, repeat_weekly, color))

            if repeat_weekly and new_date.weekday() == original_date.weekday():
                cursor.execute("INSERT INTO events (title, start, end, repeat_weekdays, repeat_monthly, repeat_weekly, color) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, new_date_str + start_time[10:], new_date_str + end_time[10:], repeat_weekdays, repeat_monthly, repeat_weekly, color))

        conn.commit()
        save_db_to_github()
        return jsonify({"message": "Robô(s) adicionado(s) com sucesso!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500






@app.route('/update_event', methods=['POST'])
def update_event():
    data = request.json
    event_id = data['id']
    title = data['title']
    start_time = data['start']
    end_time = data['end']
    repeat_weekdays = int(data.get('repeatWeekdays', False))
    repeat_monthly = int(data.get('repeatMonthly', False))
    repeat_weekly = int(data.get('repeatWeekly', False))

    # Buscar cor existente no banco para manter a mesma
    cursor.execute("SELECT color FROM events WHERE title = ?", (title,))
    result = cursor.fetchone()
    if result:
        color = result[0]
    else:
        color = generate_fixed_color(title)  # Gera uma nova cor se necessário

    try:
        # Atualiza o evento original
        cursor.execute(
            "UPDATE events SET title = ?, start = ?, end = ?, repeat_weekdays = ?, repeat_monthly = ?, repeat_weekly = ?, color = ? WHERE id = ?",
            (title, start_time, end_time, repeat_weekdays, repeat_monthly, repeat_weekly, color, event_id))
        conn.commit()

        # Remove todas as repetições antigas do evento atualizado
        cursor.execute("DELETE FROM events WHERE title = ? AND id != ?", (title, event_id))
        conn.commit()

        original_date = datetime.strptime(start_time[:10], "%Y-%m-%d")

        # Recria os eventos recorrentes com as novas configurações
        for i in range(1, 365):
            new_date = original_date + timedelta(days=i)
            new_date_str = new_date.strftime("%Y-%m-%d")

            if repeat_weekdays and new_date.weekday() < 5:
                cursor.execute(
                    "INSERT INTO events (title, start, end, repeat_weekdays, repeat_monthly, repeat_weekly, color) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, new_date_str + start_time[10:], new_date_str + end_time[10:], repeat_weekdays, repeat_monthly, repeat_weekly, color))

            if repeat_monthly and new_date.day == original_date.day:
                cursor.execute(
                    "INSERT INTO events (title, start, end, repeat_weekdays, repeat_monthly, repeat_weekly, color) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, new_date_str + start_time[10:], new_date_str + end_time[10:], repeat_weekdays, repeat_monthly, repeat_weekly, color))

            if repeat_weekly and new_date.weekday() == original_date.weekday():
                cursor.execute(
                    "INSERT INTO events (title, start, end, repeat_weekdays, repeat_monthly, repeat_weekly, color) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (title, new_date_str + start_time[10:], new_date_str + end_time[10:], repeat_weekdays, repeat_monthly, repeat_weekly, color))

        conn.commit()
        save_db_to_github()  # Salvar alterações no banco de dados
        return jsonify({"message": "Robô atualizado e recorrências geradas!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/delete_event', methods=['POST'])
def delete_event():
    data = request.json
    event_id = data['id']

    try:
        # Buscar o título do evento antes de excluir
        cursor.execute("SELECT title FROM events WHERE id = ?", (event_id,))
        event_title = cursor.fetchone()

        if event_title:
            event_title = event_title[0]

            # Excluir evento
            cursor.execute("DELETE FROM events WHERE id = ?", (event_id,))
            conn.commit()

            # Verificar se ainda existem eventos com esse título
            cursor.execute("SELECT COUNT(*) FROM events WHERE title = ?", (event_title,))
            remaining_count = cursor.fetchone()[0]

            # Se ainda houver eventos com esse nome, manter a cor
            if remaining_count > 0:
                cursor.execute("UPDATE events SET color = ? WHERE title = ?",
                               (generate_fixed_color(event_title), event_title))
                conn.commit()

        return jsonify({"message": "Robô deletado com sucesso!"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/delete_all_events', methods=['POST'])
def delete_all_events():
    data = request.json
    cursor.execute("DELETE FROM events WHERE title = ?", (data['title'],))
    conn.commit()
    return jsonify({"message": "Todos os Robôs com esse título foram deletados!"})

@app.route('/download_db')
def download_db():
    return send_file("events.db", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
