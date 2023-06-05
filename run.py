from flask import Flask, abort, redirect, url_for
from flask import request, flash
from flask import render_template, session
from pymongo import MongoClient
from datetime import datetime
from datetime import timedelta
from bson.objectid import ObjectId # id를 받아올 떄 mongodb에서는 objectid이기 떄문에 바꿔줘야 한다.
import time, math, json
from functools import wraps


app = Flask(__name__)
client = MongoClient("mongodb+srv://hyuk8:Thd980401@cluster0.cbliido.mongodb.net/?retryWrites=true&w=majority")
app.config["SECRET_KEY"] = "abcd"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=15) # 세션 유지 시간이 15분
db = client.myweb

#코인 거래소의 코인 초기화 하는 코드

# coin_exchange = db.coin_exchange
# coin={
#     "quantity":100
# }
# coin_exchange.insert_one(coin)

#로그인 기능을 함수로 정의해놓은 것.
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("id") is None or session.get("id") == "":
            return redirect(url_for("member_login", next_url = request.url))
        return f(*args, **kwargs)
    
    return decorated_function

#시간을 바꿔주는 코드
@app.template_filter("formatdatetime")
def format_datetime(value):
    if value is None:
        return ""
    
    now_timestamp = time.time()
    offset = datetime.fromtimestamp(now_timestamp) - datetime.utcfromtimestamp(now_timestamp)
    value = datetime.fromtimestamp((int(value) / 1000)) + offset
    return value.strftime('%Y-%m-%d %H:%M:%S')

#게시물들 관련 라우팅
@app.route("/list")
def lists():
    #페이지 값 ( 값이 없는 경우 기본 값은 1)
    page = request.args.get("page", default=1, type=int)
    # 한 페이지 당 몇 개의 게시물을 출력할지
    limit = request.args.get("limit", 10, type=int)

    search = request.args.get("search", -1, type=int)
    keyword = request.args.get("keyword", "",type=str)

    #최종적으로 완성된 쿼리를 만들 변수
    query = {}
    #검색어 상태를 추가할 리스트 변수
    search_list = []

    if search==0:
        search_list.append({"title": {"$regex" : keyword}})
    elif search ==1:
        search_list.append({"contents": {"$regex" : keyword}})
    elif search==2:
        search_list.append({"title": {"$regex" : keyword}})
        search_list.append({"contents": {"$regex" : keyword}})
    elif search==3:
        search_list.append({"name": {"$regex" : keyword}})
    
    #검색 대상이 한 개라도 존재할 경우 query 변수에 $or 리스트를 쿼리합니다.
    if len(search_list) > 0:
        query = {"$or": search_list}

    board = db.board
    datas = board.find(query).skip((page-1)*limit).limit(limit).sort("pubdate", -1) #db안에 있는 걸 다 가져온다.

    #게시물의 총 개수
    tot_count = board.count_documents(query)
    #마지막 페이지의 수를 구합니다.
    last_page_num = math.ceil(tot_count /limit)

    #페이지 블럭을 5개씩 표기
    block_size = 5
    #현재 블럭의 위치
    block_num = int((page-1) / block_size)
    #블럭의 시작 위치
    block_start = int((block_size * block_num) +1)
    #블럭의 끝 위치
    block_last = math.ceil(block_start + (block_size -1))

    return render_template("list.html", datas = list(datas), limit= limit, page = page, block_start = block_start, block_last = block_last, last_page_num=last_page_num,search=search, keyword=keyword)

#게시물의 상세 페이지
@app.route("/view/<idx>", methods=["GET", "POST"])
@login_required
def board_view(idx):
    if idx is not None:
        page = request.args.get("page")
        search = request.args.get("search")
        keyword = request.args.get("keyword")

        board = db.board
        data = board.find_one({"_id": ObjectId(idx)})

        if data is not None:
            result = {
                "id": data.get("_id"),
                "name": data.get("name"),
                "title": data.get("title"),
                "contents": data.get("contents"),
                "pubdate": data.get("pubdate"),
                "view": data.get("view"),
                "writer_id": data.get("writer_id", ""),
                "coin_quantity": data.get("coin_quantity"),
                "coin_price": data.get("coin_price")
            }

            if request.method == "POST":
                coin_quantity = data.get("coin_quantity")
                coin_price = data.get("coin_price")

                # 사용자 계좌 잔액 확인
                user_id = session.get("id")
                user = db.members.find_one({"_id": ObjectId(user_id)})
                user_account = user.get("account", 0)
                total_price = coin_quantity * coin_price
                current_utc_time = round(datetime.utcnow().timestamp() * 1000)

                if user_account >= total_price:
                    # 게시물 삭제
                    board.delete_one({"_id": ObjectId(idx)})

                    # 거래된 코인 가격 저장
                    coin_transactions = db.coin_transactions
                    post = {
                        "price" : coin_price,
                        "pubdate" : current_utc_time

                    }
                    coin_transactions.insert_one(post)

                    # 게시물 등록한 유저의 코인 개수와 계좌 갱신
                    writer_id = result.get("writer_id")
                    writer = db.members.find_one({"_id": ObjectId(writer_id)})
                    writer_coin_count = writer.get("coin_count", 0)
                    writer_account = writer.get("account", 0)
                    writer_coin_count -= coin_quantity
                    writer_account += total_price
                    db.members.update_one({"_id": ObjectId(writer_id)}, {"$set": {"coin_count": writer_coin_count, "account": writer_account}})

                    # 버튼을 누른 사용자의 코인 개수와 계좌 갱신
                    user_coin_count = user.get("coin_count", 0)
                    user_account -= total_price
                    user_coin_count += coin_quantity
                    db.members.update_one({"_id": ObjectId(user_id)}, {"$set": {"coin_count": user_coin_count, "account": user_account}})

                    flash("거래가 완료되었습니다. 게시물이 삭제되었습니다.")
                else:
                    flash("잔액이 부족합니다.")

                return redirect(url_for("lists", page=page, search=search, keyword=keyword))

            return render_template("view.html", result=result, page=page, search=search, keyword=keyword)
    return abort(404)


#게시물 작성 
@app.route("/write", methods=["GET", "POST"])
@login_required
def board_write():
    if request.method == "POST":
        name = request.form.get("name")
        title = request.form.get("title")
        contents = request.form.get("contents")
        coin_quantity = request.form.get("coin_count")
        coin_price = request.form.get("coin_price")

        current_utc_time = round(datetime.utcnow().timestamp() * 1000)
        board = db.board
        members = db.members

        if coin_quantity is None or coin_price is None or not coin_quantity.isdigit() or not coin_price.isdigit():
            flash("값이 들어있지 않습니다.")
            return redirect(url_for("board_write"))

        coin_quantity = int(coin_quantity)
        coin_price = int(coin_price)

        # 글쓴이의 코인 개수 확인
        writer_id = session.get("id")
        writer = members.find_one({"_id": ObjectId(writer_id)})
        writer_coin_count = writer.get("coin_count", 0)

        if coin_quantity > writer_coin_count:
            flash("코인이 부족합니다.")
            return redirect(url_for("board_write"))

        post = {
            "name": name,
            "title": title,
            "contents": contents,
            "pubdate": current_utc_time,
            "writer_id": writer_id,
            "view": 0,
            "coin_quantity": coin_quantity,
            "coin_price": coin_price,
        }

        x = board.insert_one(post)

        return redirect(url_for("board_view", idx=x.inserted_id))
    else:
        return render_template("write.html")




# 기본 페이지
@app.route("/")
def home():
    # 코인 개수와 계좌 정보 가져오기
    members = db.members
    user_id = session.get("id")
    user_coin_count = ""
    user_account = ""
    login_status = "로그인 되지 않았습니다."
    
    if user_id:
        user = members.find_one({"_id": ObjectId(user_id)})
        user_coin_count = user.get("coin_count", "")
        user_account = user.get("account", "")  # 계좌 정보 가져오기
        login_status = "로그인 중"
    
    # 코인 가격 데이터 가져오기
    coin_transactions = db.coin_transactions
    coin_data = coin_transactions.find({}, {"price": 1, "pubdate": 1, "_id": 0})
    
    # 코인 가격 목록 생성
    coin_prices = [data["price"] for data in coin_data]
    
    return render_template("index.html", coin_prices=coin_prices, coin_count=user_coin_count, account=user_account, login_status=login_status)



#회원가입
@app.route("/join", methods=["GET", "POST"])
def member_join():
    if request.method == "POST": #input값들을 입력하여 보내면 POST
        name = request.form.get("name", type=str)
        email = request.form.get("email", type=str)
        pass1 = request.form.get("pass", type=str)
        pass2 = request.form.get("pass2", type=str)

        if name == "" or email == "" or pass1 == "" or pass2 == "":
            flash("입력되지 않은 값이 있습니다.")
            return render_template("join.html")
        if pass1 != pass2:
            flash("비밀번호가 일치하지 않습니다.")
            return render_template("join.html")
        
        members = db.members
        cnt = members.count_documents({"email" : email})
        if cnt >0:
            flash("중복된 이메일 주소입니다.")
            return render_template("join.html")
        
        current_utc_time = round(datetime.utcnow().timestamp()*1000)
        post = {
            "name": name,
            "email" : email,
            "pass" : pass1,
            "joindate" : current_utc_time,
            "logintime" : "",
            "logincount" : 0,
            "coin_count" : 0,
            "account" :0
        }

        members.insert_one(post)

        return redirect(url_for("home"))
    else:
        return render_template("join.html") #처음 보이는 화면은 GET

#로그인
@app.route("/login_1", methods= ["GET", "POST"])
def member_login():
    if request.method =="POST":
        email = request.form.get("email")
        password = request.form.get("pass")
        next_url = request.form.get("next_url")

        members = db.members
        data = members.find_one({"email" : email})

        if data is None:
            flash("회원 정보가 없습니다.")
            return redirect(url_for("member_login"))
        else:
            if data.get("pass") ==password:
                session["email"] = email
                session["name"] = data.get("name")
                session["id"] = str(data.get("_id"))
                session.permanent = True # permanent의 역할은 session은 서버의 자원을 이용하는데 일정시간 동안 접속 안하면 세션을 닫아줌.
                if next_url is not None:
                    return redirect(next_url)
                else:
                    return redirect(url_for("home"))
                
            else:
                flash("비밀번호가 일치하지 않습니다.")
                return redirect(url_for("member_login"))

        return ""
    else:
        next_url = request.args.get("next_url", type=str)
        if next_url is not None:
            return render_template("login_1.html", next_url = next_url)
        else:
            return render_template("login_1.html")

#글 수정하기
@app.route("/edit/<idx>", methods=["GET", "POST"])
@login_required
def board_edit(idx):
    if request.method == "GET":
        board = db.board
        data = board.find_one({"_id": ObjectId(idx)})

        if data is None:
            flash("해당 게시물이 존재하지 않습니다.")
            return redirect(url_for("lists"))
        elif session.get("id") != data.get("writer_id"):
            flash("글 수정 권한이 없습니다.")
            return redirect(url_for("lists"))
        else:
            return render_template("edit.html", data=data)

    elif request.method == "POST":
        title = request.form.get("title")
        contents = request.form.get("contents")

        board = db.board
        data = board.find_one({"_id": ObjectId(idx)})

        if session.get("id") != data.get("writer_id"):
            flash("글 수정 권한이 없습니다.")
            return redirect(url_for("lists"))
        else:
            board.update_one(
                {"_id": ObjectId(idx)},
                {
                    "$set": {
                        "title": title,
                        "contents": contents,
                    }
                }
            )
            flash("수정되었습니다.")
            return redirect(url_for("board_view", idx=idx))

    return abort(404)

    
#글 삭제하기
@app.route("/delete/<idx>")
def board_delete(idx):
    board = db.board
    data = board.find_one({"_id": ObjectId(idx)})
    if data.get("writer_id") == session.get("id"):
        board.delete_one({"_id": ObjectId(idx)})
        flash("삭제 되었습니다.")
    else:
        flash("삭제 권한이 없습니다.")

    return redirect(url_for("lists"))

#계좌에 돈 넣기
@app.route("/deposit", methods=["POST"])
@login_required
def deposit():
    amount = request.form.get("amount")
    if amount:
        try:
            amount = int(amount)
        except ValueError:
            flash("유효한 금액을 입력하세요.")
            return redirect(url_for("account"))
        
        members = db.members
        member_id = ObjectId(session.get("id"))
        member = members.find_one({"_id": member_id})
        if member:
            current_account = member.get("account", 0)
            updated_account = current_account + amount
            members.update_one(
                {"_id": member_id},
                {"$set": {"account": updated_account}}
            )
            flash("성공적으로 들어갔습니다.")
        else:
            flash("계정을 찾을 수 없습니다.")
    else:
        flash("금액을 입력하세요.")

    return redirect(url_for("account"))

# 계좌에서 돈 빼기
@app.route("/withdraw", methods=["POST"])
@login_required
def withdraw():
    amount = request.form.get("amount")
    if amount:
        try:
            amount = int(amount)
        except ValueError:
            flash("유효한 금액을 입력하세요.")
            return redirect(url_for("account"))
        
        members = db.members
        member_id = ObjectId(session.get("id"))
        member = members.find_one({"_id": member_id})
        if member:
            current_account = member.get("account", 0)
            if current_account >= amount:
                updated_account = current_account - amount
                members.update_one(
                    {"_id": member_id},
                    {"$set": {"account": updated_account}}
                )
                flash("성공적으로 출금되었습니다.")
            else:
                flash("잔액이 부족합니다.")
        else:
            flash("계정을 찾을 수 없습니다.")
    else:
        flash("금액을 입력하세요.")

    return redirect(url_for("account"))


@app.route("/account")
@login_required
def account():
    return render_template("account.html")

@app.route("/logout")
def member_logout():
    # 세션 제거
    session.clear()
    flash("로그아웃되었습니다.")
    return redirect(url_for("home"))


# 코인 거래소의 코인
@app.route("/coin_exchange")
def coin_exchange():
    coin_exchange = db.coin_exchange
    coin = coin_exchange.find_one()  # 코인 거래소의 코인 정보를 가져옵니다.

    if not coin:
        # 초기 코인 거래소의 코인 정보 설정
        initial_coin = {
            "price": 100,  # 초기 가격을 100원으로 설정
            "quantity": 100  # 초기 코인 수량 설정
        }
        coin_exchange.insert_one(initial_coin)
        coin = coin_exchange.find_one()

    coin_transaction = db.coin_transactions
    latest_transaction_count = coin_transaction.count_documents({})

    if latest_transaction_count > 0:
        latest_transaction = coin_transaction.find().sort("pubdate", -1).limit(1)
        latest_price = latest_transaction[0].get("price")

        if latest_price is not None:
            coin_exchange.update_one(
                {"_id": '646ba92b7d40855d1a9fe8fd'},
                {"$set": {"price": latest_price}}
            )
            coin = coin_exchange.find_one()  # 업데이트된 코인 정보를 다시 가져옵니다.

    return render_template("coin_exchange.html", coin=coin)


@app.route("/buy_coin", methods=["POST"])
@login_required
def buy_coin():
    coin_exchange = db.coin_exchange
    coin = coin_exchange.find_one()  # 코인 거래소의 코인 정보를 가져옵니다.

    if coin:
        coin_id = str(coin.get("_id"))
        amount = int(request.form.get("amount"))

        coin_transaction = db.coin_transactions
        latest_transaction_count = coin_transaction.count_documents({})
        latest_transaction = coin_transaction.find().sort("timestamp", -1).limit(1)

        latest_price = None
        if latest_transaction_count > 0:
            latest_price = latest_transaction[0].get("price")

        if latest_price is not None:
            coin_exchange.update_one(
                {"_id": "646ba92b7d40855d1a9fe8fd"},  # 모든 문서를 업데이트합니다.
                {"$set": {"price": latest_price}}
            )
            coin = coin_exchange.find_one()  # 업데이트된 코인 정보를 다시 가져옵니다.

        price = coin.get("price")
        total_cost = price * amount

        members = db.members
        member_id = ObjectId(session.get("id"))
        member = members.find_one({"_id": member_id})
        account = member.get("account", 0)

        if total_cost > account:
            flash("잔액이 부족합니다.")
        else:
            # 코인을 구매한 사용자의 계정 정보 업데이트
            updated_account = account - total_cost
            members.update_one(
                {"_id": member_id},
                {"$set": {"account": updated_account}},
            )

            # 사용자의 "coin_count" 필드 업데이트 (코인 개수 증가)
            updated_coin_count = member.get("coin_count", 0) + amount
            members.update_one(
                {"_id": member_id},
                {"$set": {"coin_count": updated_coin_count}},
            )

            # 코인 거래소의 코인 정보 업데이트 (수량 감소)
            updated_quantity = coin.get("quantity") - amount
            coin_exchange.update_one(
                {},  # 모든 문서를 업데이트합니다.
                {"$set": {"quantity": updated_quantity}},
            )

            flash("코인을 구매하였습니다.")
    else:
        flash("코인 정보를 찾을 수 없습니다.")

    return redirect(url_for("coin_exchange"))

@app.route("/update_price", methods=["POST"])
@login_required
def update_price():
    coin_exchange = db.coin_exchange
    coin_transactions = db.coin_transactions

    coin = coin_exchange.find_one()
    coin_id = coin["_id"]

    latest_transaction = coin_transactions.find().sort("pubdate", -1).limit(1)
    latest_price = latest_transaction[0]["price"] if coin_transactions.count_documents({}) > 0 else None

    if latest_price is not None:
        coin_exchange.update_one(
            {"_id": coin_id},
            {"$set": {"price": latest_price}}
        )
        flash("가격이 업데이트되었습니다.")
    else:
        flash("최근 거래가 없어 가격을 업데이트할 수 없습니다.")

    return redirect(url_for("coin_exchange"))

   
if __name__ =="__main__":
    app.run(host="0.0.0.0", debug=True, port=9000)
