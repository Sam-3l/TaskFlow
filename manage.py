from app import create_app, db

app = create_app()

def reset_db():
    with app.app_context():
        db.drop_all()
        db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
