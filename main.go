package main

import (
	"bytes"
	"context"
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"html/template"
	"io/ioutil"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"sync"
	"time"

	"golang.org/x/sync/errgroup"
)

func main() {
	log.SetFlags(0)

	http.Handle("/favicon.ico", http.NotFoundHandler())
	http.Handle("/", &handler{
		store: make(map[string][]byte),
		luccaClient: LuccaClient{
			addr:     os.Getenv("LUCCA_ADDR"),
			login:    os.Getenv("LUCCA_LOGIN"),
			password: os.Getenv("LUCCA_PASSWORD"),
		},
		tmpl: template.Must(template.ParseFiles("templates/index.html")),

		legalEntity:        os.Getenv("LEGAL_ENTITY"),
		swapExclusion:      os.Getenv("SWAP_EXCLUSION"),
		swapLunchExclusion: os.Getenv("SWAP_LUNCH_EXCLUSION"),
	})

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	log.Fatal(http.ListenAndServe(":"+port, nil))
}

type handler struct {
	store       map[string][]byte
	luccaClient LuccaClient
	tmpl        *template.Template

	legalEntity                       string
	swapExclusion, swapLunchExclusion string
}

func (h *handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if b, ok := h.store[r.URL.Path[1:]]; ok {
		fmt.Fprintf(w, "%s", b)
		return
	}

	resource, err := h.handle(r.Context())
	if err != nil {
		log.Print(err)
		code := http.StatusInternalServerError
		http.Error(w, http.StatusText(code), code)
		return
	}

	timestamp := time.Now().UnixNano()
	csvPath := fmt.Sprintf("swap-%d.csv", timestamp)
	resource.CSVPath = csvPath
	h.store[csvPath] = resource.csv
	xlsxPath := fmt.Sprintf("swap-%d.xlsx", timestamp)
	resource.XLSXPath = xlsxPath
	h.store[xlsxPath] = resource.xls

	if err := h.tmpl.Execute(w, resource); err != nil {
		log.Print(err)
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
}

type Resource struct {
	CSVHeader         []string
	CSVPath, XLSXPath string
	csv, xls          []byte

	Records []ResourceRecord
}

type ResourceRecord struct {
	Name       string
	Department string
	Goes       string
	LunchTeam  string
}

func (h *handler) handle(ctx context.Context) (*Resource, error) {
	models, err := h.fetch(ctx)
	if err != nil {
		return nil, err
	}

	csvOut, err := h.runAlgo(ctx, models)
	if eerr, ok := err.(*exec.ExitError); ok {
		return nil, errors.New(string(eerr.Stderr))
	} else if err != nil {
		return nil, err
	}

	xlsOut, err := csvToXLS(ctx, csvOut)
	if eerr, ok := err.(*exec.ExitError); ok {
		return nil, errors.New(string(eerr.Stderr))
	} else if err != nil {
		return nil, err
	}

	resource := Resource{csv: csvOut, xls: xlsOut}
	records, _ := csv.NewReader(bytes.NewReader(csvOut)).ReadAll()
	resource.CSVHeader = records[0]
	for _, record := range records[1:] {
		resource.Records = append(resource.Records, ResourceRecord{
			Name:       record[0],
			Department: record[1],
			Goes:       record[2],
			LunchTeam:  record[3],
		})
	}
	return &resource, nil
}

type Model struct {
	Name, Department, LegalEntity string
	HalfDayLeaves                 int
}

func (h *handler) fetch(ctx context.Context) ([]Model, error) {
	var (
		leaves []luccaLeave
		users  []luccaUser
		err    error
	)

	// do two requests concurrently
	g, ctx := errgroup.WithContext(ctx)
	g.Go(func() error {
		leaves, err = h.luccaClient.fetchLeaves(ctx)
		return err
	})
	g.Go(func() error {
		users, err = h.luccaClient.fetchUsers(ctx)
		return err
	})
	if err := g.Wait(); err != nil {
		return nil, err
	}

	userLeaves := make(map[string]int)
	for _, leave := range leaves {
		userLeaves[leave.LeavePeriod.Owner.Name]++
	}

	var models []Model
	for _, user := range users {
		if h.legalEntity != "" && user.LegalEntity.Name != h.legalEntity {
			continue
		}
		models = append(models, Model{
			Name:          user.Name,
			Department:    user.Department.Name,
			LegalEntity:   user.LegalEntity.Name,
			HalfDayLeaves: userLeaves[user.Name],
		})
	}
	return models, nil
}

type LuccaClient struct {
	addr            string
	login, password string

	sync.Mutex
	cookie string
}

type luccaUser struct {
	Name       string `json:"name"`
	Department struct {
		Name string `json:"name"`
	} `json:"department"`
	LegalEntity struct {
		Name string `json:"name"`
	} `json:"legalEntity"`
}

func (c *LuccaClient) fetchUsers(ctx context.Context) ([]luccaUser, error) {
	if err := c.doLogin(ctx); err != nil {
		return nil, err
	}

	query := url.Values{"fields": []string{"name,department[name],legalEntity[name]"}}
	url := c.addr + "/api/v3/users?" + query.Encode()
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Cookie", c.cookie)

	resp, err := http.DefaultClient.Do(req.WithContext(ctx))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, err := ioutil.ReadAll(resp.Body)
		if err != nil {
			return nil, err
		}
		return nil, fmt.Errorf(`Get %s: got status %d and body %q`, url, resp.StatusCode, body)
	}

	var users struct {
		Data struct {
			Items []luccaUser `json:"items"`
		} `json:"data"`
	}
	err = json.NewDecoder(resp.Body).Decode(&users)
	return users.Data.Items, err
}

type luccaLeave struct {
	LeavePeriod struct {
		Owner struct {
			Name string `json:"name"`
		} `json:"owner"`
	} `json:"leavePeriod"`
}

func (c *LuccaClient) fetchLeaves(ctx context.Context) ([]luccaLeave, error) {
	if err := c.doLogin(ctx); err != nil {
		return nil, err
	}

	monday, friday := nextSwap()
	query := url.Values{
		"date": []string{fmt.Sprintf(
			"between,%s,%s",
			monday.Format("2006-01-02"),
			friday.Format("2006-01-02"),
		)},
		"fields":                          []string{"leavePeriod[owner[name]]"},
		"leavePeriod.owner.legalEntityID": []string{"1"},
	}
	url := c.addr + "/api/v3/leaves?" + query.Encode()
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Cookie", c.cookie)

	resp, err := http.DefaultClient.Do(req.WithContext(ctx))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		body, err := ioutil.ReadAll(resp.Body)
		if err != nil {
			return nil, err
		}
		return nil, fmt.Errorf(`Get %s: got status %d and body %q`, url, resp.StatusCode, body)
	}

	var leaves struct {
		Data struct {
			Items []luccaLeave `json:"items"`
		} `json:"data"`
	}
	err = json.NewDecoder(resp.Body).Decode(&leaves)
	return leaves.Data.Items, err
}

func nextSwap() (monday, friday time.Time) {
	year, month, day := time.Now().Date()
	today := time.Date(year, month, day, 0, 0, 0, 0, time.Local)
	monday = today
	for monday.Weekday() != time.Monday {
		monday = monday.Add(24 * time.Hour)
	}
	friday = monday.Add(4 * 24 * time.Hour)
	return monday, friday
}

// doLogin sets c.cookie. It returns early if c.cookie is already set.
// It is safe to use from different goroutines
func (c *LuccaClient) doLogin(ctx context.Context) error {
	c.Lock()
	defer c.Unlock()
	if c.cookie != "" {
		return nil
	}

	req, err := http.NewRequest(http.MethodPost, c.addr+"/login", strings.NewReader(url.Values{
		"Login":           []string{c.login},
		"Password":        []string{c.password},
		"PersistentCooke": []string{"false"},
	}.Encode()))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	var httpClient = &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}

	resp, err := httpClient.Do(req.WithContext(ctx))
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	cookies := resp.Cookies()
	if len(cookies) != 1 {
		return errors.New("couldn't login to lucca, credentials are probably wrong")
	}
	c.cookie = cookies[0].String()
	return nil
}

// runAlgo build the csv input for swap.py, runs swap.py and returns csv output
func (h *handler) runAlgo(ctx context.Context, users []Model) ([]byte, error) {
	buf := new(bytes.Buffer)
	csvWriter := csv.NewWriter(buf)
	if err := csvWriter.Write([]string{"name", "department", "legal-entity", "half-day-leaves"}); err != nil {
		return nil, err
	}
	var records [][]string
	for _, u := range users {
		records = append(records,
			[]string{u.Name, u.Department, u.LegalEntity, strconv.Itoa(u.HalfDayLeaves)},
		)
	}
	if err := csvWriter.WriteAll(records); err != nil {
		return nil, err
	}

	cmd := exec.CommandContext(ctx, "python3", "swap.py")
	cmd.Env = []string{
		"PYTHONIOENCODING=utf-8",
		"SWAP_EXCLUSION=" + h.swapExclusion,
		"SWAP_LUNCH_EXCLUSION=" + h.swapLunchExclusion,
	}
	cmd.Stdin = buf
	return cmd.Output()
}

func csvToXLS(ctx context.Context, b []byte) ([]byte, error) {
	cmd := exec.CommandContext(ctx, "python3", "csv_to_xlsx.py")
	cmd.Env = []string{"PYTHONIOENCODING=utf-8"}
	cmd.Stdin = bytes.NewReader(b)
	return cmd.Output()
}
