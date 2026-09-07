import streamlit as st
import requests
from datetime import date, timedelta
from zoneinfo import ZoneInfo


# ---------------------------------------------------------
# 1. 기본 설정
# ---------------------------------------------------------

st.set_page_config(
    page_title="KOBIS 박스오피스",
    page_icon="🎬",
    layout="wide",
)

st.title("🎬 KOBIS 일일 박스오피스")
st.caption("영화관입장권통합전산망(KOBIS) 일일 박스오피스")


# ---------------------------------------------------------
# 2. 한국 시간 기준으로 오늘과 어제 날짜 계산
# ---------------------------------------------------------
# 배포 서버의 시간이 한국 시간이 아닐 수 있으므로
# 반드시 한국 시간(KST)을 기준으로 날짜를 계산합니다.

KST = ZoneInfo("Asia/Seoul")

today_kst = date.today()
# date.today()는 서버의 날짜를 사용할 수 있으므로
# 실제 한국 시간의 날짜를 datetime으로 구한 뒤 date로 변환합니다.
today_kst = __import__("datetime").datetime.now(KST).date()

yesterday_kst = today_kst - timedelta(days=1)


# ---------------------------------------------------------
# 3. 날짜 선택
# ---------------------------------------------------------
# 사용자는 과거 날짜부터 '어제'까지 선택할 수 있습니다.
# 오늘 이후 날짜는 선택할 수 없습니다.

selected_date = st.date_input(
    "조회할 날짜를 선택하세요",
    value=yesterday_kst,
    max_value=yesterday_kst,
    help="오늘 박스오피스는 아직 집계 전이므로 어제까지 선택할 수 있습니다.",
)

# KOBIS API가 요구하는 날짜 형식: YYYYMMDD
target_date = selected_date.strftime("%Y%m%d")

# 화면에 보여 줄 날짜
display_date = selected_date.strftime("%Y년 %m월 %d일")


# ---------------------------------------------------------
# 4. KOBIS API 호출 함수
# ---------------------------------------------------------
# 같은 날짜를 다시 조회하면 API를 다시 호출하지 않고
# 약 1시간 동안 캐시된 결과를 사용합니다.
#
# target_dt를 함수의 인자로 넣었기 때문에
# 날짜가 바뀌면 날짜별로 별도의 캐시가 만들어집니다.

@st.cache_data(ttl=3600)
def get_boxoffice(target_dt, api_key):
    url = (
        "https://www.kobis.or.kr/"
        "kobisopenapi/webservice/rest/boxoffice/"
        "searchDailyBoxOfficeList.json"
    )

    params = {
        "key": api_key,
        "targetDt": target_dt,
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=10,
        )

        # HTTP 상태 코드가 200이 아니면 오류로 처리합니다.
        response.raise_for_status()

        data = response.json()

    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "message": (
                "KOBIS API에 접속하지 못했습니다.\n\n"
                "다음 사항을 확인해 주세요.\n"
                "- 인터넷 연결 상태\n"
                "- KOBIS API 서버 상태\n"
                "- 요청 주소가 올바른지\n"
                f"- 접속 오류 내용: {e}"
            ),
            "movies": [],
        }

    except ValueError:
        return {
            "success": False,
            "message": (
                "KOBIS API가 정상적인 JSON 데이터를 보내지 않았습니다.\n\n"
                "KOBIS API 서버 상태나 요청 내용을 확인해 주세요."
            ),
            "movies": [],
        }

    # -----------------------------------------------------
    # 5. faultInfo 확인
    # -----------------------------------------------------
    # KOBIS는 인증키가 틀려도 HTTP 상태코드가 200일 수 있습니다.
    # 따라서 응답 안에 faultInfo가 있는지도 확인해야 합니다.

    if "faultInfo" in data:
        fault_info = data["faultInfo"]

        fault_message = (
            fault_info.get("message")
            or fault_info.get("faultString")
            or "KOBIS API에서 오류를 반환했습니다."
        )

        return {
            "success": False,
            "message": (
                "KOBIS API에서 오류를 반환했습니다.\n\n"
                f"오류 내용: {fault_message}\n\n"
                "다음 사항을 확인해 주세요.\n"
                "- Streamlit Secrets에 KOBIS_KEY가 있는지\n"
                "- KOBIS_KEY가 정확한 인증키인지\n"
                "- KOBIS Open API 사용 권한이 정상인지"
            ),
            "movies": [],
        }

    # -----------------------------------------------------
    # 6. 영화 목록 가져오기
    # -----------------------------------------------------

    boxoffice_result = data.get("boxOfficeResult", {})
    movie_list = boxoffice_result.get("dailyBoxOfficeList", [])

    # 목록이 비어 있으면 '아직 집계 전'으로 안내합니다.
    if not movie_list:
        return {
            "success": False,
            "empty": True,
            "message": (
                "그날은 아직 집계 전입니다.\n\n"
                "KOBIS에서 해당 날짜의 일일 박스오피스 데이터가 "
                "아직 제공되지 않는 것으로 보입니다."
            ),
            "movies": [],
        }

    # -----------------------------------------------------
    # 7. 숫자 문자열을 실제 숫자로 변환
    # -----------------------------------------------------
    # KOBIS API에서는 숫자도 문자열로 전달됩니다.
    # 정렬, 조건 검사, 그래프 등에 사용하기 위해 int로 변환합니다.

    movies = []

    for movie in movie_list:
        try:
            converted_movie = {
                "rank": int(movie.get("rank", 0)),
                "rankInten": int(movie.get("rankInten", 0)),
                "movieNm": movie.get("movieNm", ""),
                "openDt": movie.get("openDt", ""),
                "audiCnt": int(movie.get("audiCnt", 0)),
                "audiAcc": int(movie.get("audiAcc", 0)),
                "scrnCnt": int(movie.get("scrnCnt", 0)),
            }

            movies.append(converted_movie)

        except (ValueError, TypeError):
            # 숫자로 변환할 수 없는 데이터가 있으면
            # 해당 영화는 건너뜁니다.
            continue

    if not movies:
        return {
            "success": False,
            "empty": False,
            "message": (
                "KOBIS에서 영화 목록을 받았지만 숫자 데이터를 "
                "정상적으로 변환하지 못했습니다.\n\n"
                "KOBIS API 응답 형식이 변경되었는지 확인해 주세요."
            ),
            "movies": [],
        }

    # 순위를 숫자 기준으로 정렬합니다.
    movies.sort(key=lambda movie: movie["rank"])

    return {
        "success": True,
        "empty": False,
        "message": "",
        "movies": movies,
    }


# ---------------------------------------------------------
# 8. Secrets에서 인증키 가져오기
# ---------------------------------------------------------
# 인증키를 코드에 직접 적지 않습니다.
#
# Streamlit Cloud의 Secrets에 다음처럼 등록합니다.
#
# KOBIS_KEY = "본인의_인증키"
#
# 실제 인증키는 main.py에 작성하지 않습니다.

try:
    api_key = st.secrets["KOBIS_KEY"]

except KeyError:
    st.error(
        "KOBIS_KEY를 찾을 수 없습니다.\n\n"
        "Streamlit Cloud의 앱 설정에서 Secrets를 열고 "
        "`KOBIS_KEY`라는 이름으로 KOBIS 인증키를 등록했는지 확인해 주세요."
    )
    st.stop()


# ---------------------------------------------------------
# 9. 선택한 날짜의 박스오피스 조회
# ---------------------------------------------------------

result = get_boxoffice(target_date, api_key)


# ---------------------------------------------------------
# 10. 오류 처리
# ---------------------------------------------------------

if not result["success"]:
    # 영화 목록이 비어 있는 경우에는 특별한 안내를 보여 줍니다.
    if result.get("empty", False):
        st.info("📅 그날은 아직 집계 전입니다.")
        st.caption(
            f"{display_date}의 KOBIS 일일 박스오피스 데이터가 "
            "아직 제공되지 않는 것으로 보입니다."
        )
    else:
        st.warning(result["message"])

    st.stop()


movies = result["movies"]


# ---------------------------------------------------------
# 11. 조회 날짜 표시
# ---------------------------------------------------------

st.subheader(f"📅 {display_date}")

st.caption(
    "선택한 날짜의 KOBIS 일일 박스오피스"
)


# ---------------------------------------------------------
# 12. 1위 영화의 주요 지표
# ---------------------------------------------------------

first_movie = movies[0]

st.subheader("🏆 1위 영화")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "관객수",
        f"{first_movie['audiCnt']:,}명",
    )

with col2:
    st.metric(
        "누적관객",
        f"{first_movie['audiAcc']:,}명",
    )

with col3:
    st.metric(
        "스크린수",
        f"{first_movie['scrnCnt']:,}개",
    )

# 누적관객 100만 명 이상이면 트로피를 붙입니다.
first_movie_name = first_movie["movieNm"]

if first_movie["audiAcc"] >= 1_000_000:
    first_movie_name += " 🏆"

st.markdown(f"### 🎞️ {first_movie_name}")


# ---------------------------------------------------------
# 13. 관객수 상위 5편 막대그래프
# ---------------------------------------------------------

st.subheader("📊 관객수 상위 5편")

# 관객수가 많은 영화부터 정렬해서 상위 5편을 가져옵니다.
top5 = sorted(
    movies,
    key=lambda movie: movie["audiCnt"],
    reverse=True,
)[:5]

# Streamlit 차트용 데이터
chart_data = {
    movie["movieNm"]: movie["audiCnt"]
    for movie in top5
}

st.bar_chart(
    chart_data,
    x_label="영화",
    y_label="관객수",
)


# ---------------------------------------------------------
# 14. 전체 박스오피스 표
# ---------------------------------------------------------

st.subheader("🎬 전체 박스오피스")

table_data = []

for movie in movies:

    # 영화명 옆에 100만 관객 돌파 트로피 표시
    movie_name = movie["movieNm"]

    if movie["audiAcc"] >= 1_000_000:
        movie_name += " 🏆"

    # 전날 대비 순위 증감 표시
    rank_inten = movie["rankInten"]

    if rank_inten > 0:
        # 양수: 순위가 올랐으므로 빨간 위 화살표
        rank_change = f"🔺 {rank_inten}"

    elif rank_inten < 0:
        # 음수: 순위가 내렸으므로 파란 아래 화살표
        rank_change = f"🔻 {abs(rank_inten)}"

    else:
        # 0: 순위 변동 없음
        rank_change = "—"

    table_data.append(
        {
            "순위": movie["rank"],
            "증감": rank_change,
            "영화명": movie_name,
            "개봉일": movie["openDt"],
            "관객수": movie["audiCnt"],
            "누적관객": movie["audiAcc"],
            "스크린수": movie["scrnCnt"],
        }
    )


st.dataframe(
    table_data,
    use_container_width=True,
    hide_index=True,
    column_config={
        "순위": st.column_config.NumberColumn(
            "순위",
            format="%d",
        ),
        "증감": st.column_config.TextColumn(
            "전일 대비",
        ),
        "영화명": st.column_config.TextColumn(
            "영화명",
        ),
        "개봉일": st.column_config.TextColumn(
            "개봉일",
        ),
        "관객수": st.column_config.NumberColumn(
            "관객수",
            format="%,d",
        ),
        "누적관객": st.column_config.NumberColumn(
            "누적관객",
            format="%,d",
        ),
        "스크린수": st.column_config.NumberColumn(
            "스크린수",
            format="%,d",
        ),
    },
)


# ---------------------------------------------------------
# 15. 안내 문구
# ---------------------------------------------------------

st.caption(
    "🔺 빨간 위 화살표: 전날보다 순위 상승 · "
    "🔻 파란 아래 화살표: 전날보다 순위 하락 · "
    "🏆 누적관객 100만 명 이상"
)

st.caption(
    "데이터 출처: 영화관입장권통합전산망(KOBIS) 일일 박스오피스 Open API"
)
