function f(x){
    return Number(x || 0).toFixed(1);
}

async function loadWeather(){

    const r = await fetch("/station");
    const d = await r.json();

    document.getElementById("temp").innerHTML =
        `${f(d.temp)}°`;

    document.getElementById("feels").innerHTML =
        `${f(d.temp - 1.2)}°`;

    document.getElementById("humidity").innerHTML =
        `${f(d.humidity)}%`;

    document.getElementById("pressure").innerHTML =
        `${f(d.pressure)} hPa`;

    document.getElementById("wind").innerHTML =
        `${f(d.wind_ms)} m/s`;

    document.getElementById("windDir").innerHTML =
        `${f(d.wind_dir || 0)}°`;

    document.getElementById("gust").innerHTML =
        `${f(d.wind_gust_ms)} m/s`;

    document.getElementById("rain").innerHTML =
        `${f(d.rain_24h)} mm`;
}

async function loadForecast(){

    const r = await fetch("/forecast7");
    const d = await r.json();

    let html = "";

    for(let i=0;i<7;i++){

        html += `
        <div class="forecast-item">

            <div>${d.daily.time[i]}</div>

            <h2 style="margin:10px 0;">
                ${f(d.daily.temperature_2m_max[i])}°
            </h2>

            <div>
                ${f(d.daily.temperature_2m_min[i])}°
            </div>

        </div>
        `;
    }

    document.getElementById("forecast").innerHTML = html;
}

async function loadChart(){

    const r = await fetch("/history_flat");
    const data = await r.json();

    if(!Array.isArray(data)) return;

    const labels = data.map(i =>
        new Date(i.timestamp).toLocaleTimeString()
    );

    const temps = data.map(i => i.temp);

    const ctx =
        document.getElementById("chart");

    new Chart(ctx,{
        type:"line",

        data:{
            labels:labels,

            datasets:[{
                label:"Temperature",

                data:temps,

                borderColor:"#3b82f6",

                tension:0.4
            }]
        },

        options:{
            responsive:true,

            plugins:{
                legend:{
                    labels:{
                        color:"white"
                    }
                }
            },

            scales:{
                x:{
                    ticks:{
                        color:"white"
                    }
                },

                y:{
                    ticks:{
                        color:"white"
                    }
                }
            }
        }
    });
}

window.onload = () => {

    loadWeather();

    loadForecast();

    loadChart();

    setInterval(loadWeather,60000);
};