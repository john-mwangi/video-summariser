import configparser
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from main import main
from pydantic import BaseModel

from video_summarizer.backend.configs import config
from video_summarizer.backend.utils import auth
from video_summarizer.backend.utils.utils import logger

API_PREFIX = config.ApiSettings.load_settings().api_prefix

parser = configparser.ConfigParser()
parser.read(config.ROOT_DIR / "pyproject.toml")
version = parser["tool.poetry"]["version"].replace('"', "")
description = parser["tool.poetry"]["description"].replace('"', "")


class VideoUrls(BaseModel):
    channels: list[str] = []
    videos: list[str] = []
    limit_transcript: float | int | None = 0.25
    top_n: int = 2
    sort_by: str = "newest"


app = FastAPI(
    title="ChatGPT Video Summarizer", description=description, version=version
)

router_v1 = APIRouter()


@router_v1.post("/token")
def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> auth.Token:
    user = auth.authenticate_user(
        fake_db=auth.fake_users_db,
        username=form_data.username,
        password=form_data.password,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_access_token(data={"sub": user.username})
    return auth.Token(access_token=access_token, token_type="bearer")


@router_v1.post(path="/summarize_video")
def fetch_video_summary(
    video_urls: Annotated[VideoUrls, Depends(auth.get_current_active_user)]
):
    """Summarize a video using AI:

    Args:
    ---
    * channels: a list of channels to retrive a video(s) to summarise from based on `sort_by` and `top_n` parameters\n
    * video: a list of video urls to summarise\n
    * limit_transcript: portion of the video transcript to summarise
    (None=full, <1 = partial, >=1 = number of chuncks)\n
    * top_n: retrieves this number of video from a channel to summarise\n
    * sort_by: sorts `top_n`

    Returns:
    ---
    A list of video summaries
    """

    with open(config.params_path, "r") as f:
        responses = yaml.safe_load(f).get("responses")

    try:
        summaries = main(
            channels=video_urls.channels,
            videos=video_urls.videos,
            LIMIT_TRANSCRIPT=video_urls.limit_transcript,
            sort_by=video_urls.sort_by,
            top_n=video_urls.top_n,
        )

        data = {"data": {"summaries": summaries}}
        status = responses.get("SUCCESS")
        status_code = config.statuses.SUCCESS.value

    except Exception as e:
        logger.exception(e)
        data = {"summaries": None}
        status = responses.get("ERROR")
        status_code = config.statuses.ERROR.value

    return JSONResponse(content={**data, **status}, status_code=status_code)


# Mount the router on the app
app.include_router(router_v1, prefix=API_PREFIX)
